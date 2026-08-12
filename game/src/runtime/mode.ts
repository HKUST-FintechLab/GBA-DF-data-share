export type RuntimeMode = "coordinator" | "client";

export function getRuntimeMode(): RuntimeMode {
  const mode = new URLSearchParams(window.location.search).get("mode");
  return mode === "client" ? "client" : "coordinator";
}
