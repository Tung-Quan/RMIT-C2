import axios from "axios";
import {io as createSocket} from "socket.io-client";
import {API_BASE_URL, API_ORIGIN, api} from "./client";
import {tideAdapter} from "./tideTransport";
export const CHAT_API_BASE_URL=`${API_BASE_URL}/chat`;
export const chatApi=axios.create({baseURL:CHAT_API_BASE_URL,adapter:tideAdapter});
export function createChatSocket(){
 const socket=createSocket(API_ORIGIN,{path:"/careers-socket.io",transports:["websocket"],auth:async callback=>{try{const result=await api.post("/chat-ticket",{});callback({ticket:result.data.ticket});}catch{callback({ticket:""});}}});
 socket.on("disconnect",reason=>{if(reason==="io server disconnect")socket.connect();});return socket;
}
function encodeHeaderText(value) {
  return encodeURIComponent(String(value || ""));
}

export function buildChatUserHeaders() { return {}; }



export function getChatUsers(user) {
  return chatApi.get("/api/messages/users", {
    headers: buildChatUserHeaders(user)
  });
}

export function getCurrentChatUser(user) {
  return chatApi.get("/api/auth/check-auth", {
    headers: buildChatUserHeaders(user)
  });
}

export function getDirectMessages(userId, user) {
  return chatApi.get(`/api/messages/${userId}`, {
    headers: buildChatUserHeaders(user)
  });
}

export function sendDirectMessage(userId, payload, user) {
  return chatApi.post(`/api/messages/send/${userId}`, payload, {
    headers: buildChatUserHeaders(user)
  });
}

export function getChatGroups(user) {
  return chatApi.get("/api/groups", {
    headers: buildChatUserHeaders(user)
  });
}

export function createChatGroup(payload, user) {
  return chatApi.post("/api/groups/create", payload, {
    headers: buildChatUserHeaders(user)
  });
}

export function getGroupMessages(groupId, user) {
  return chatApi.get(`/api/groups/${groupId}/messages`, {
    headers: buildChatUserHeaders(user)
  });
}

export function sendGroupMessage(groupId, payload, user) {
  return chatApi.post(`/api/groups/${groupId}/send`, payload, {
    headers: buildChatUserHeaders(user)
  });
}
