import {api} from "./client";
export const getCurrentUser=()=>api.get("/auth/me");
