import http from "@/api/http";

export function getSysInfo() {
  return http.get("/wx/sys/info");
}

export function getSysResources() {
  return http.get("/wx/sys/resources");
}
