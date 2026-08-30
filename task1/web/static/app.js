function fmt(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function fmtMoney(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

let selectedPharmacyId = null;

function selectedArea() {
  const value = document.getElementById("areaFilter").value;
  return value === "All areas" ? "" : value;
}

function queryParams() {
  const ds = document.getElementById("dateStart").value;
  const de = document.getElementById("dateEnd").value;
  const area = selectedArea();
  const p = new URLSearchParams();
  if (ds) p.set("date_start", ds);
  if (de) p.set("date_end", de);
  if (area) p.set("area", area);
  return p;
}

async function loadSummary() {
  const res = await fetch("/api/summary?" + queryParams());
  const data = await res.json();
  renderSummary(data);
  renderTables(data);
  renderQuality(data);
}

function renderQuality(data) {
  const s = data.summary || {}, q = data.data_quality || {};
  document.getElementById("qualitySummary").innerHTML = `<p>Matched aliases: ${fmt(s.identity_stats.aliases_matched)} (${q.matched_alias_pct || 0}% of all supplier accounts) · Ambiguous aliases: ${fmt(s.identity_stats.aliases_ambiguous)} (${q.ambiguous_alias_pct || 0}%) · Unmatched aliases: ${fmt(s.identity_stats.aliases_unmatched)} (${q.unmatched_alias_pct || 0}%) · Total supplier accounts: ${fmt(s.identity_stats.aliases_total)}</p><p>Matched ERP invoice rows: ${fmt(s.identity_stats.erp_invoices_matched)} (${q.matched_erp_invoice_pct || 0}%) · Unknown areas: ${fmt(s.unknown_area_pharmacy_count)} · Ambiguous areas: ${fmt(s.ambiguous_area_pharmacy_count || 0)} · Recovered areas: ${fmt(s.recovered_area_pharmacy_count)} · Conflicting evidence: ${fmt(s.area_conflict_pharmacy_count)}</p><p class="muted">Rule money impact represents revenue affected before final aggregation; it is not the final dashboard revenue.</p>`;
  fillTable("cleaningImpact", data.cleaning_impact || [], (r) => `<tr><td>${r.rule_id}</td><td>${fmt(r.rows_affected)}</td><td>${fmtMoney(r.monetary_impact_egp)}</td><td>${r.description}</td></tr>`);
}

function renderSummary(data) {
  const s = data.summary;
  const cards = [
    ["Total revenue (EGP)", fmtMoney(data.meta.total_revenue_egp)],
    ["Unique invoice rows", fmt(data.meta.total_orders)],
    ["Active pharmacies", fmt(data.meta.pharmacy_count)],
    ["Suppliers", fmt(data.meta.supplier_count)],
    ["Unmatched ERP invoice rows", fmt(s.unmatched_erp_invoice_count)],
    ["Unmatched supplier accounts", fmt(s.unmatched_alias_count)],
    ["Unknown areas", fmt(s.unknown_area_pharmacy_count)],
    ["Ambiguous areas", fmt(s.ambiguous_area_pharmacy_count || 0)],
  ];
  document.getElementById("summaryCards").innerHTML = cards
    .map(([label, value]) => `<div class="card stat-card"><div class="value">${value}</div><div class="label">${label}</div></div>`)
    .join("");
}

function renderAreaTop(area) {
  const rows = ((window.latestSummary || {}).top_pharmacies_by_area || {})[area] || [];
  const container = document.getElementById("topByArea");
  if (!area) {
    container.innerHTML = '<p class="muted">Select an area to view its top pharmacies.</p>';
    return;
  }
  if (!rows.length) {
    container.innerHTML = `<h3>${area}</h3><p class="muted">No revenue for the selected area and date range.</p>`;
    return;
  }
  container.innerHTML = `<h3>${area}</h3><table><thead><tr><th>Rank</th><th>Pharmacy</th><th>Revenue</th><th>Orders</th></tr></thead><tbody>${rows.slice(0, 20).map((r, i) => `<tr data-pharmacy-id="${r.pharmacy_id}"><td>${i + 1}</td><td>${r.canonical_name}</td><td>${fmtMoney(r.revenue_egp)}</td><td>${fmt(r.order_count)}</td></tr>`).join("")}</tbody></table>`;
  container.querySelectorAll("[data-pharmacy-id]").forEach((row) => row.addEventListener("click", () => showPharmacy(Number(row.dataset.pharmacyId))));
}

function renderTables(data) {
  window.latestSummary = data;
  fillTable("pharmaciesPerArea", data.pharmacies_per_area, (r) =>
    `<tr><td>${r.resolved_area || r.area || "—"}</td><td>${fmt(r.pharmacy_count)}</td></tr>`
  );
  fillTable("revenuePerArea", data.revenue_per_area, (r) =>
    `<tr><td>${r.resolved_area}</td><td>${fmtMoney(r.revenue_egp)}</td><td>${fmt(r.order_count)}</td></tr>`
  );
  fillTable("topPharmacies", data.top_pharmacies, (r, i) =>
    `<tr data-pharmacy-id="${r.pharmacy_id}"><td>${i + 1}</td><td>${r.canonical_name}</td><td>${r.resolved_area || "—"}</td><td>${fmtMoney(r.revenue_egp)}</td><td>${fmt(r.order_count)}</td></tr>`
  );
  fillTable("topSuppliers", data.top_suppliers, (r, i) =>
    `<tr><td>${i + 1}</td><td>${r.supplier_name || r.supplier_key}</td><td>${fmtMoney(r.revenue_egp)}</td><td>${fmt(r.order_count)}</td><td>${fmt(r.pharmacies_served)}</td></tr>`
  );
  const byArea = data.top_pharmacies_by_area || {};
  const areaSelect = document.getElementById("topAreaSelect");
  const areas = Object.keys(byArea).sort();
  areaSelect.innerHTML = '<option value="">Select area</option>' + areas.map((area) => `<option value="${area}">${area}</option>`).join("");
  areaSelect.onchange = () => renderAreaTop(areaSelect.value);
  renderAreaTop(areaSelect.value);
  document.querySelectorAll("[data-pharmacy-id]").forEach((row) => row.addEventListener("click", () => showPharmacy(Number(row.dataset.pharmacyId))));
  document.querySelectorAll("#pharmaciesPerArea tbody tr").forEach((row, index) => row.addEventListener("click", () => {
    const area = (data.pharmacies_per_area || [])[index];
    if (area) {
      document.getElementById("areaFilter").value = area.resolved_area;
      loadSummary();
      loadPharmacies();
    }
  }));
  document.querySelectorAll("#revenuePerArea tbody tr").forEach((row, index) => row.addEventListener("click", () => {
    const area = (data.revenue_per_area || [])[index];
    if (area) {
      document.getElementById("areaFilter").value = area.resolved_area;
      loadSummary();
      loadPharmacies();
    }
  }));
}

function fillTable(id, rows, rowFn) {
  const body = document.querySelector(`#${id} tbody`);
  body.innerHTML = (rows || []).map(rowFn).join("") || `<tr><td colspan="8" class="muted">No revenue for the selected date range.</td></tr>`;
}

async function loadPharmacies() {
  const area = selectedArea();
  const q = document.getElementById("pharmacySearch").value;
  const p = new URLSearchParams();
  if (area) p.set("area", area);
  if (q) p.set("q", q);
  const res = await fetch("/api/pharmacies?" + p);
  const list = await res.json();
  const ul = document.getElementById("pharmacyList");
  const unique = [];
  const seen = new Set();
  list.forEach((pharmacy) => {
    const id = pharmacy.master_pharmacy_id ?? pharmacy.pharmacy_id;
    if (!seen.has(id)) {
      seen.add(id);
      unique.push(pharmacy);
    }
  });
  if (!unique.length) {
    selectedPharmacyId = null;
    document.getElementById("pharmacyDetail").hidden = true;
    ul.innerHTML = `<li class="muted">${q ? "No pharmacies found." : "No pharmacies available for this filter."}</li>`;
    return;
  }
  if (selectedPharmacyId !== null && !unique.some((p) => Number(p.master_pharmacy_id ?? p.pharmacy_id) === selectedPharmacyId)) {
    selectedPharmacyId = null;
    document.getElementById("pharmacyDetail").hidden = true;
    document.querySelector("#detailPanel > .muted").hidden = false;
  }
  ul.innerHTML = unique
    .map(
      (p) =>
        `<li data-id="${p.master_pharmacy_id ?? p.pharmacy_id}">${p.canonical_name}<span class="badge">${p.resolved_area || "unknown"}</span></li>`
    )
    .join("");
  ul.querySelectorAll("li").forEach((li) => {
    li.addEventListener("click", () => showPharmacy(Number(li.dataset.id)));
  });
}

async function showPharmacy(id) {
  selectedPharmacyId = id;
  const area = selectedArea();
  if (area) {
    const candidate = (await fetch(`/api/pharmacies?area=${encodeURIComponent(area)}`)).json();
    const allowed = await candidate;
    if (!allowed.some((p) => Number(p.master_pharmacy_id ?? p.pharmacy_id) === id)) return;
  }
  document.querySelectorAll("#pharmacyList li").forEach((li) => li.classList.toggle("active", Number(li.dataset.id) === id));
  const res = await fetch(`/api/pharmacy/${id}?` + queryParams());
  const p = await res.json();
  const el = document.getElementById("pharmacyDetail");
  el.hidden = false;
  el.innerHTML = `
    <h3>${p.canonical_name}</h3>
    <p><strong>Master pharmacy ID:</strong> ${p.master_pharmacy_id}</p>
    <p><strong>Area:</strong> ${p.resolved_area || "Unknown"} ${p.area_confidence ? `<span class="badge">${p.area_confidence}</span>` : ""}</p>
    <p><strong>Resolution method:</strong> ${p.area_source || "unknown"}</p>
    <p><strong>Evidence:</strong> Registry: ${p.registry_area || "missing"}; invoice evidence: ${fmt(p.area_evidence_count)}; conflicting evidence: ${fmt(p.conflicting_evidence_count)}${p.area_conflict ? " (conflict retained)" : ""}</p>
    <p><strong>Revenue (filtered):</strong> ${fmtMoney(p.total_revenue_egp)} (${fmt(p.order_count)} orders)</p>
    <h4>Supplier aliases (${(p.aliases || []).length})</h4>
    <table class="alias-table"><thead><tr><th>Account name</th><th>Supplier</th><th>Branch</th><th>Code</th><th>Match method / score</th></tr></thead><tbody>
      ${(p.aliases || []).length ? (p.aliases || [])
        .map(
          (a) =>
            `<tr><td>${a.account_name}</td><td>${a.parent_company || ""}</td><td>${a.branch_tag || a.branch_id}</td><td>${a.supplier_code != null ? a.supplier_code : "—"}</td><td>${a.match_method || ""} / ${a.match_score != null ? a.match_score.toFixed(1) : "—"}</td></tr>`
        )
        .join("") : '<tr><td colspan="5" class="muted">No matched supplier aliases for this pharmacy.</td></tr>'}
    </tbody></table>
    <h4>Revenue over time</h4>
    <table><thead><tr><th>Month</th><th>Revenue (EGP)</th></tr></thead><tbody>
      ${(p.revenue_by_month || []).map((m) => `<tr><td>${m.month}</td><td>${fmtMoney(m.revenue_egp)}</td></tr>`).join("")}
    </tbody></table>
  `;
}

async function loadUnmatched() {
  const res = await fetch("/api/unmatched");
  const data = await res.json();
  const s = data.summary;
  document.getElementById("unmatchedSummary").innerHTML = `
    <p>Unmatched ERP revenue (EGP): <strong>${fmtMoney(s.unmatched_erp_revenue_egp)}</strong></p>
    <p>Aliases matched: ${fmt(s.identity_stats.aliases_matched)} · Ambiguous: ${fmt(s.identity_stats.aliases_ambiguous)} · Unmatched: ${fmt(s.identity_stats.aliases_unmatched)} · Total: ${fmt(s.identity_stats.aliases_total)}</p>
    <p>ERP invoices matched: ${fmt(s.identity_stats.erp_invoices_matched)} / ${fmt(s.identity_stats.erp_invoices_total)}</p>
  `;
  const erpSample = (data.unmatched_erp_sample || []).slice(0, 10);
  const aliasSample = (data.unmatched_aliases_sample || []).slice(0, 10);
  document.querySelector("#unmatchedErp").closest("details").querySelector("summary").textContent = `Sample unmatched ERP invoices — showing ${erpSample.length} of ${fmt(s.unmatched_erp_invoice_count)} rows`;
  document.querySelector("#unmatchedAliases").closest("details").querySelector("summary").textContent = `Sample unmatched supplier accounts — showing ${aliasSample.length} of ${fmt(s.unmatched_alias_count)} accounts`;
  fillTable("unmatchedErp", erpSample, (r) =>
    `<tr><td>${r.invoice_no || "—"}</td><td>${r.account_name || "—"}</td><td>${r.branch_code || "—"}</td><td>${r.entry_date || "—"}</td><td>${r.total_after_discount != null ? fmtMoney(r.total_after_discount) : "—"}</td><td>${r.match_status || r.match_method || "—"}</td></tr>`
  );
  fillTable("unmatchedAliases", aliasSample, (r) =>
    `<tr><td>${r.account_name || "—"}</td><td>${r.parent_company || r.supplier_code || "—"}</td><td>${r.branch_tag || r.branch_id || "—"}</td><td>${r.match_score != null ? Number(r.match_score).toFixed(1) : "—"}</td><td>${r.match_status || r.match_method || "—"}</td></tr>`
  );
}

async function initAreas() {
  const res = await fetch("/api/summary");
  const data = await res.json();
  const sel = document.getElementById("areaFilter");
  (data.meta.areas || []).forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a;
    opt.textContent = a;
    sel.appendChild(opt);
  });
}

document.getElementById("applyFilters").addEventListener("click", () => {
  loadSummary();
  loadPharmacies();
});
document.getElementById("pharmacySearch").addEventListener("input", () => loadPharmacies());

initAreas().then(() => {
  loadSummary();
  loadPharmacies();
  loadUnmatched();
});
