import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api.js";
import { Account, Ask, Clients, DataIn, Outlook, Overview } from "./pages.jsx";

const TABS = [["", "Overview"], ["clients", "Clients"], ["outlook", "Outlook"], ["data", "Add data"]];
const route = () => location.hash.replace(/^#\/?/, "");

function App() {
  const [r, setR] = useState(route()), [version, setVersion] = useState(0), [busy, setBusy] = useState(false);
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem("arm_user") || "null")?.name);
  const [ask, setAsk] = useState({ open: false, q: "", n: 0 });
  useEffect(() => {
    const h = () => { setR(route()); window.scrollTo(0, 0); };
    addEventListener("hashchange", h);
    return () => removeEventListener("hashchange", h);
  }, []);
  const go = (to) => { location.hash = "/" + to; };
  const loaded = () => { setVersion((v) => v + 1); go(""); };
  const demo = async () => { setBusy(true); try { await api.demo(); loaded(); } finally { setBusy(false); } };
  const openAsk = (q = "") => setAsk((a) => ({ open: true, q, n: a.n + 1 }));
  const props = { version, go };
  return (
    <>
      <header className="top">
        <a className="brand" href="#/"><span className="mark" aria-hidden="true" />Risk Manager</a>
        {user ? (
          <span className="who">{user} <button className="link" onClick={() => { localStorage.removeItem("arm_user"); setUser(null); }}>Sign out</button></span>
        ) : <a className="link" href="#/account">Sign in</a>}
      </header>
      <main>
        {r === "clients" ? <Clients {...props} /> : r === "outlook" ? <Outlook {...props} /> :
          r === "data" ? <DataIn onLoaded={loaded} onDemo={api.demo} busy={busy} /> :
          r === "account" ? <Account onAuthed={(n) => { setUser(n); go(""); }} /> :
          <Overview {...props} onDemo={demo} busy={busy} ask={openAsk} />}
      </main>
      <nav className="dock" aria-label="Main">
        {TABS.map(([k, l]) => <a key={k} href={"#/" + k} aria-current={r === k ? "page" : undefined}>{l}</a>)}
        <button onClick={() => openAsk()}>Ask</button>
      </nav>
      <Ask open={ask.open} seed={ask} onClose={() => setAsk((a) => ({ ...a, open: false }))} />
    </>
  );
}

createRoot(document.getElementById("root")).render(<App />);
