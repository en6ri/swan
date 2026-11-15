/* SWAN: stan przeczytania (kropka), licznik, „dziś”, wyszukiwarka i skrót „/”. Bez śledzenia. */
(function () {
  var KEY = "swan:read";
  var root = document.documentElement;
  root.classList.add("js");

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; }
  }
  function save(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list.slice(-500))); } catch (e) { /* tryb prywatny */ }
  }

  var read = load();
  var readSet = {};
  read.forEach(function (slug) { readSet[slug] = true; });

  var article = document.querySelector("[data-article]");
  if (article) {
    var slug = article.getAttribute("data-article");
    if (!readSet[slug]) { read.push(slug); readSet[slug] = true; save(read); }
  }

  function markRead(scope) {
    var seen = {}, total = 0, done = 0;
    (scope || document).querySelectorAll("[data-slug]").forEach(function (el) {
      var s = el.getAttribute("data-slug");
      if (readSet[s]) el.classList.add("is-read");
      if (!seen[s]) { seen[s] = true; total++; if (readSet[s]) done++; }
    });
    return { total: total, done: done };
  }
  var stats = markRead();
  var counter = document.querySelector("[data-counter]");
  if (counter && stats.total) counter.textContent = "Przeczytane " + stats.done + " z " + stats.total;

  // Wydanie sprzed dnia: „Dziś” zamienia się na neutralny tekst.
  var edition = document.querySelector("[data-edition]");
  if (edition) {
    var d = new Date();
    var today = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
    if (edition.getAttribute("data-edition") !== today) {
      document.querySelectorAll("[data-today]").forEach(function (el) {
        el.textContent = el.getAttribute("data-other");
      });
    }
  }

  // „/” otwiera wyszukiwarkę.
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
    var tag = (e.target && e.target.tagName) || "";
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
    var link = document.querySelector("[data-search-link]");
    var input = document.querySelector("[data-search] input");
    e.preventDefault();
    if (input) input.focus(); else if (link) location.href = link.href;
  });

  // Wyszukiwarka.
  var box = document.querySelector("[data-search]");
  if (!box) return;
  var input = box.querySelector("input");
  var results = box.querySelector("[data-results]");
  var index = null;

  function norm(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/\p{M}/gu, "").replace(/ł/g, "l");
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }
  function render() {
    var q = norm(input.value.trim());
    results.textContent = "";
    if (!q || !index) return;
    var words = q.split(/\s+/);
    var hits = index.filter(function (p) {
      var hay = norm(p.t + " " + p.l + " " + p.c);
      return words.every(function (w) { return hay.indexOf(w) !== -1; });
    });
    if (!hits.length) { results.appendChild(el("p", "empty", "Nic nie znaleziono.")); return; }
    hits.slice(0, 50).forEach(function (p) {
      var row = el("article", "row item");
      row.setAttribute("data-slug", p.s);
      var body = el("div", "row-body");
      var h = el("h3", "row-title");
      var dot = el("span", "dot");
      dot.setAttribute("aria-hidden", "true");
      var a = el("a", "stretch", p.t);
      a.href = p.u;
      h.appendChild(dot); h.appendChild(a);
      body.appendChild(h);
      body.appendChild(el("p", "meta", p.c + " · " + p.d + " · " + p.m));
      row.appendChild(body);
      results.appendChild(row);
    });
    markRead(results);
  }
  input.addEventListener("input", render);
  fetch(box.getAttribute("data-index"))
    .then(function (r) { return r.json(); })
    .then(function (data) { index = data; render(); })
    .catch(function () { results.appendChild(el("p", "empty", "Nie udało się wczytać wyszukiwarki.")); });
})();
