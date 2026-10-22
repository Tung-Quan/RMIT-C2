import {verifyGateway,resolveTideChatUser} from "./tideGateway.js";
// The browser's Tide DPoP proof is verified by FairEnrol Express before this private hop.
// This route accepts only the short-lived HMAC gateway assertion and pins its chat audience;
// accepting the browser DPoP token here would bypass that boundary, not improve DPoP support.
export async function ProtectedRoute(req,res,next){try{const header=req.headers.authorization||"";if(!header.startsWith("Bearer "))throw new Error("Missing gateway assertion");const claims=await verifyGateway(header.slice(7),"careers-chat",req);req.user=await resolveTideChatUser(claims);next();}catch{res.status(401).json({success:false,message:"Invalid or replayed Tide gateway assertion"});}}
