const local = ["localhost", "127.0.0.1"].includes(location.hostname) || location.hostname.endsWith(".onrender.com");
window.API_BASE = local ? "" : "https://YOUR-SERVICE.onrender.com";
