import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createHash, randomUUID } from "node:crypto";
import { PGlite } from "@electric-sql/pglite";
import { SignJWT, calculateJwkThumbprint, exportJWK, generateKeyPair, jwtVerify } from "jose";
import { createApp } from "../server/app.js";
import { initializeDatabase, linkIdentity } from "../server/db.js";

const origin = "http://migration.test", issuer = "http://localhost:8080/realms/fairenrol";
const secret = "a-private-migration-test-key-that-is-not-used-in-production";
let database, db, server, upstream, base, realmKey, proofKey, publicProof, thumbprint;
const received = [];
before(async () => {
  database = new PGlite();
  db = { query: (q,a) => !a && q.includes(";") ? database.exec(q).then(r=>r.at(-1)) : database.query(q,a), transaction: fn=>database.transaction(fn) };
  await initializeDatabase(db);
  for (const personId of ["registrar-1", "s17"]) await linkIdentity(db,{issuer,subject:personId,personId});
  realmKey = await generateKeyPair("EdDSA",{extractable:true});
  proofKey = await generateKeyPair("ES256",{extractable:true});
  publicProof = await exportJWK(proofKey.publicKey); thumbprint = await calculateJwkThumbprint(publicProof);
  const publicKey = {...await exportJWK(realmKey.publicKey),kid:"migration-vvk",alg:"EdDSA"};
  upstream = createServer(async (req,res) => {
    const chunks=[]; for await (const chunk of req) chunks.push(chunk);
    const body=Buffer.concat(chunks);
    const {payload}=await jwtVerify(req.headers.authorization.slice(7),new TextEncoder().encode(secret),{algorithms:["HS256"],issuer:"fairenrol-careers-gateway",audience:req.url.startsWith("/api/")?"careers-chat":"careers-api"});
    assert.equal(payload.path,req.url); assert.equal(payload.method,req.method);
    assert.equal(payload.body_sha256,createHash("sha256").update(body).digest("hex"));
    received.push({payload,headers:req.headers,body});
    res.writeHead(200,{"content-type":"application/json"});res.end(JSON.stringify({role:payload.role,person:payload.person_id,body:body.toString("base64")}));
  }).listen(0,"127.0.0.1");
  await new Promise(r=>upstream.once("listening",r));
  const url=`http://127.0.0.1:${upstream.address().port}`;
  server=createApp({db,adapter:{realm:"fairenrol",resource:"fairenrol-client","auth-server-url":"http://localhost:8080",jwk:{keys:[publicKey]}},appOrigin:origin,careers:{apiUrl:url,chatUrl:url,secret}}).listen(0,"127.0.0.1");
  await new Promise(r=>server.once("listening",r));base=`http://127.0.0.1:${server.address().port}`;
});
after(async()=>{await new Promise(r=>server?.close(r));await new Promise(r=>upstream?.close(r));await database?.close();});

async function headers(person,path,method="GET") {
  const now=Math.floor(Date.now()/1000);
  const token=await new SignJWT({iss:issuer,sub:person,azp:"fairenrol-client",exp:now+300,iat:now,realm_access:{roles:[person==="registrar-1"?"registrar":"student"]},cnf:{jkt:thumbprint}}).setProtectedHeader({alg:"EdDSA",kid:"migration-vvk"}).sign(realmKey.privateKey);
  const proof=await new SignJWT({jti:randomUUID(),htm:method,htu:new URL(path,origin).href.split("?")[0],iat:now,ath:createHash("sha256").update(token).digest("base64url")}).setProtectedHeader({alg:"ES256",typ:"dpop+jwt",jwk:publicProof}).sign(proofKey.privateKey);
  return {Authorization:`DPoP ${token}`,DPoP:proof};
}

test("career endpoints require a verified signed token and proof before forwarding",async()=>{
  const n=received.length;
  assert.equal((await fetch(base+"/api/careers/auth/me")).status,401);
  const h=await headers("s17","/api/careers/auth/me");delete h.DPoP;
  assert.equal((await fetch(base+"/api/careers/auth/me",{headers:h})).status,401);
  assert.equal(received.length,n);
});
test("gateway derives identity and role from verified claims and strips impersonation headers",async()=>{
  const path="/api/careers/auth/me";
  const result=await fetch(base+path,{headers:{...await headers("s17",path),"X-User-Id":"registrar-1","X-User-Name":"Forged","X-User-Email":"forged@example.invalid"}});
  assert.equal(result.status,200); assert.deepEqual(await result.json(),{role:"candidate",person:"s17",body:""});
  const last=received.at(-1);assert.equal(last.headers["x-user-id"],undefined);assert.equal(last.headers.dpop,undefined);assert.equal(last.payload.tide_subject,"s17");assert.equal(last.payload.email,null);
});
test("registrar hiring role is explicit and multipart document bytes survive unchanged",async()=>{
  const path="/api/careers/candidate/documents?force=false",body=Buffer.from("--boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"proof.txt\"\r\n\r\nCV\u0000bytes\r\n--boundary--");
  const response=await fetch(base+path,{method:"POST",headers:{...await headers("registrar-1",path,"POST"),"Content-Type":"multipart/form-data; boundary=boundary","Idempotency-Key":"document-once"},body});
  assert.equal(response.status,200);assert.equal((await response.json()).role,"hr");assert.deepEqual(received.at(-1).body,body);assert.equal(received.at(-1).headers["idempotency-key"],"document-once");
});
test("replayed DPoP cannot cause a second upstream mutation",async()=>{
  const path="/api/careers/hr/jobs",h={...await headers("registrar-1",path,"POST"),"Content-Type":"application/json"},body=JSON.stringify({role:"admin",title:"Replay test"});
  const n=received.length;assert.equal((await fetch(base+path,{method:"POST",headers:h,body})).status,200);assert.equal((await fetch(base+path,{method:"POST",headers:h,body})).status,401);assert.equal(received.length,n+1);assert.equal(received.at(-1).payload.role,"hr");
});
test("password login and unguarded upload URLs are unavailable",async()=>{
  for(const [path,expected]of[["/api/careers/auth/login",410],["/api/careers/uploads/private.txt",404]]){
    assert.equal((await fetch(base+path,{headers:await headers("s17",path)})).status,expected);
  }
});
test("chat REST assertions and socket tickets have separate audiences",async()=>{
  const path="/api/careers/chat/api/auth/check-auth";
  assert.equal((await fetch(base+path,{headers:await headers("s17",path)})).status,200);assert.equal(received.at(-1).payload.aud,"careers-chat");
  const ticketPath="/api/careers/chat-ticket";
  const result=await fetch(base+ticketPath,{method:"POST",headers:await headers("s17",ticketPath,"POST")});assert.equal(result.status,200);
  const {ticket}=await result.json();const {payload}=await jwtVerify(ticket,new TextEncoder().encode(secret),{audience:"careers-chat-connect",issuer:"fairenrol-careers-gateway",algorithms:["HS256"]});
  assert.equal(payload.tide_subject,"s17");assert.ok(payload.exp-payload.iat<=30);assert.equal(payload.path,undefined);
});
test("gateway cannot forward assertions to another origin or arbitrary private endpoints",async()=>{
  const n=received.length;
  for(const path of ["/api/careers/%5cexternal.example/secret", "/api/careers/metrics"]){
    assert.equal((await fetch(base+path,{headers:await headers("s17",path)})).status,404);
  }
  assert.equal(received.length,n);
});
test("inactive FairEnrol accounts cannot acquire an career session or chat ticket",async()=>{
  await db.query("UPDATE people SET active=false WHERE id='s17'");
  const path="/api/careers/chat-ticket";const n=received.length;
  assert.equal((await fetch(base+path,{method:"POST",headers:await headers("s17",path,"POST")})).status,403);assert.equal(received.length,n);
});
