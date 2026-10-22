import {createContext,useContext,useEffect,useMemo,useRef,useState} from "react";
import {useTideCloak} from "@tidecloak/react";
import {bindTideTransport} from "../api/tideTransport";
import {api,clearLocalSession,clearStoredToken,getErrorMessage} from "../api/client";
const AuthContext=createContext(null);
export function AuthProvider({children}) {
 const tide=useTideCloak(); const [user,setUser]=useState(null), [loading,setLoading]=useState(true),[error,setError]=useState("");
 const [retryKey,setRetryKey]=useState(0);
 const transport=useRef(tide);transport.current=tide;
 bindTideTransport((...args)=>{if(!transport.current.authenticated||transport.current.isInitializing)throw new Error("Sign in with TideCloak first.");return transport.current.secureFetch(...args);});
 useEffect(()=>{clearStoredToken();},[]);
 useEffect(()=>{let done=false; if(tide.isInitializing)return; if(!tide.authenticated){setUser(null);setLoading(false);return;}setLoading(true);api.get("/auth/me").then(r=>{if(!done){const previous=sessionStorage.getItem("fairenrol:careers-user");if(previous && previous!==String(r.data.id))clearLocalSession();sessionStorage.setItem("fairenrol:careers-user",String(r.data.id));setUser(r.data);setError("");}}).catch(e=>{if(!done){setUser(null);setError(getErrorMessage(e));}}).finally(()=>{if(!done)setLoading(false);});return()=>{done=true;};},[tide.isInitializing,tide.authenticated,retryKey]);
 const value=useMemo(()=>({user,initializing:tide.isInitializing||loading,isAuthenticated:tide.authenticated&&Boolean(user),hasTideSession:tide.authenticated,error:error||tide.initError?.message||"",retry:()=>setRetryKey(k=>k+1),login:async()=>{sessionStorage.setItem("fairenrol:postLogin","/careers/index.html");await tide.login();},logout:()=>{clearLocalSession();sessionStorage.removeItem("fairenrol:careers-user");return tide.logout();}}),[user,loading,error,tide]);
 return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useAuth(){const value=useContext(AuthContext);if(!value)throw new Error("AuthProvider is missing");return value;}
