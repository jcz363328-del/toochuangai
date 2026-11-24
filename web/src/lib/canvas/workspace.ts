export const isAPlusWorkspace = new URLSearchParams(window.location.search).get("workspace") === "a_plus";
export const canvasWorkspaceTitle = isAPlusWorkspace ? "A+画布" : "无限画布";
