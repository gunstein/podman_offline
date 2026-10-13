const element = (id) => document.getElementById(id);
const basePath = new URL(".", location.href).pathname.replace(/\/$/, "");
let csrf = "";
async function api(path, method = "GET", body) {
  const response = await fetch(basePath + path, {
    method,
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) throw new Error(`The request failed (${response.status})`);
  return response.status === 204 ? null : response.json();
}
async function refresh() {
  const todos = await api("/api/todos");
  element("todos").replaceChildren();
  for (const todo of todos) {
    const row = document.createElement("li");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = todo.done;
    checkbox.onchange = () => action(async () => {
      await api(`/api/todos/${todo.id}`, "PATCH", {done: checkbox.checked});
      await refresh();
    });
    const label = document.createElement("span");
    label.textContent = ` ${todo.title} `;
    const remove = document.createElement("button");
    remove.textContent = "Delete";
    remove.onclick = () => action(async () => {
      await api(`/api/todos/${todo.id}`, "DELETE");
      await refresh();
    });
    row.append(checkbox, label, remove);
    element("todos").append(row);
  }
}
async function action(fn) {
  element("error").textContent = "";
  try { await fn(); }
  catch (error) { element("error").textContent = error.message; }
}
element("form").onsubmit = (event) => {
  event.preventDefault();
  action(async () => {
    await api("/api/todos", "POST", {title: element("title").value});
    element("title").value = "";
    await refresh();
  });
};
element("logout").onclick = () => action(async () => {
  await api("/auth/logout", "POST");
  location.reload();
});
action(async () => {
  const state = await api("/auth/me");
  if (!state.user) {
    element("user").textContent = "Sign in to see your tasks.";
    return;
  }
  csrf = state.csrf;
  element("user").textContent = `Signed in as ${state.user.name}`;
  element("login").hidden = true;
  element("logout").hidden = false;
  element("form").hidden = false;
  await refresh();
});
