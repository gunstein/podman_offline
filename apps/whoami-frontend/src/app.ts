// Signed-in state and claims from this app's backend; tokens never reach the browser.
export {};
interface User {
  sub: string;
  name: string;
}
interface Me {
  user: User | null;
  csrf: string;
}
interface Claim {
  type: string;
  value: string;
}

const element = <T extends HTMLElement>(id: string): T => {
  const found = document.getElementById(id);
  if (!found) throw new Error(`Missing element ${id}`);
  return found as T;
};
const basePath = new URL(".", location.href).pathname.replace(/\/$/, "");
let csrf = "";

async function api<T>(path: string, method = "GET"): Promise<T | null> {
  const response = await fetch(basePath + path, {
    method,
    headers: { "X-CSRF-Token": csrf },
  });
  if (!response.ok) throw new Error(`The request failed (${response.status})`);
  return response.status === 204 ? null : ((await response.json()) as T);
}

function showClaims(claims: Claim[]): void {
  const body = element<HTMLTableElement>("claims").tBodies[0];
  body.replaceChildren();
  for (const claim of claims) {
    const row = body.insertRow();
    row.insertCell().textContent = claim.type;
    row.insertCell().textContent = claim.value;
  }
  element("claims").hidden = false;
}

async function action(work: () => Promise<void>): Promise<void> {
  element("error").textContent = "";
  try {
    await work();
  } catch (error) {
    element("error").textContent = error instanceof Error ? error.message : String(error);
  }
}

element<HTMLButtonElement>("logout").onclick = () =>
  action(async () => {
    await api<null>("/auth/logout", "POST");
    location.reload();
  });

void action(async () => {
  const me = await api<Me>("/auth/me");
  if (!me?.user) {
    element("user").textContent = "Sign in to see your claims.";
    element("login").hidden = false;
    return;
  }
  csrf = me.csrf;
  element("user").textContent = `Signed in as ${me.user.name}`;
  element("logout").hidden = false;
  showClaims((await api<Claim[]>("/api/claims")) ?? []);
});
