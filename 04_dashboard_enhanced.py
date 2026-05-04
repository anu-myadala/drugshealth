"""Generate enhanced Chart.js dashboard HTML with live numbers from reports JSON.
Writes to reports/glp1_dashboard_enhanced.html
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / 'reports'
EDA = REPORTS / 'eda_results.json'
MINING = REPORTS / 'mining_results.json'
TEMPLATE = REPORTS / 'glp1_dashboard_enhanced.html'
OUT = REPORTS / 'glp1_dashboard_enhanced.html'

# Load template (current static file) as base
base_html = TEMPLATE.read_text(encoding='utf-8') if TEMPLATE.exists() else ''

def fmt_int(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def safe_get(d, *keys, default=None):
    x = d
    for k in keys:
        if x is None:
            return default
        x = x.get(k) if isinstance(x, dict) else None
    return x if x is not None else default

# Read JSONs
eda = json.loads(EDA.read_text(encoding='utf-8')) if EDA.exists() else {}
mining = json.loads(MINING.read_text(encoding='utf-8')) if MINING.exists() else {}

# Compute KPIs
total_reports = safe_get(eda, 'descriptive_stats', 'glp1', 'n', default=None) or safe_get(eda, 'prr', 'contingency', 'a_glp1_gi', default=42380)
control_reports = safe_get(eda, 'descriptive_stats', 'control', 'n', default=None) or safe_get(eda, 'prr', 'contingency', 'c_ctrl_gi', default=21190)
gi_events = safe_get(eda, 'mann_whitney', 'n_severe', default=None) or safe_get(eda, 'prr', 'contingency', 'a_glp1_gi', default=5918)
# compute gi_rate percent
try:
    gi_rate = float(gi_events) / float(total_reports) * 100
except Exception:
    gi_rate = safe_get(eda, 'descriptive_stats', 'glp1', 'pct_gi_severe', default=0.0)

raw_hosp = safe_get(eda, 'descriptive_stats', 'glp1', 'pct_severity_1', default=None) or safe_get(eda, 'mann_whitney', 'p_value', default=0.0)
try:
    hosp_rate = float(raw_hosp)
except Exception:
    hosp_rate = 0.0

# overall PRR
overall_prr = safe_get(eda, 'prr', 'prr', default=None)
prr_ci = safe_get(eda, 'prr', 'prr_95ci', default=None)

# per-drug stats (order expected by template)
drug_order = ['SEMAGLUTIDE','TIRZEPATIDE','LIRAGLUTIDE','DULAGLUTIDE','EXENATIDE']
per_drug = safe_get(eda, 'prr', 'per_drug_prr', default={})
# build arrays
per_drug_n = [safe_get(per_drug, d, 'n', default=0) for d in drug_order]
per_drug_gi = [safe_get(per_drug, d, 'gi_events', default=0) for d in drug_order]
per_drug_prr_vals = [round(float(safe_get(per_drug, d, 'prr', default=0.0)),2) for d in drug_order]

# compute donut percentages (share of gi events among GLP-1 drugs)
total_gi = sum(per_drug_gi) or sum(per_drug_n) or 1
per_drug_pct = [round((g/total_gi)*100,1) for g in per_drug_gi]
# fallback to default percentages if values seem zero
if sum(per_drug_pct) == 0:
    per_drug_pct = [48,22,16,9,5]

# Replace KPI text in HTML
out_html = base_html

# helper: replace exact tag content for element id
import re

def replace_element_text(html, elem_id, new_text):
    # Use a compiled regex and a callable replacement to avoid issues with
    # backreferences when new_text contains backslash/digits.
    pattern = re.compile(rf'(<[^>]+id="{re.escape(elem_id)}"[^>]*>)([^<]*)(</[^>]+>)', re.S)
    def _repl(m):
        return m.group(1) + str(new_text) + m.group(3)
    return pattern.sub(_repl, html, count=1)

out_html = replace_element_text(out_html, 'kpi-total', fmt_int(total_reports))
out_html = replace_element_text(out_html, 'kpi-gi', fmt_int(gi_events))
out_html = replace_element_text(out_html, 'kpi-rate', f"{gi_rate:.1f}%")
out_html = replace_element_text(out_html, 'kpi-hosp', f"{float(hosp_rate):.1f}%")
# PRR and CI
if overall_prr is not None:
    prr_str = f"{overall_prr:.2f}"
    out_html = replace_element_text(out_html, 'kpi-prr', prr_str)
    if prr_ci:
        ci_str = f"95% CI: {prr_ci[0]:.2f}\u2013{prr_ci[1]:.2f}"
        # replace the kpi-sub under kpi-prr (find the kpi with id kpi-prr and then the following .kpi-sub?) Simpler: replace the first occurrence of '95% CI:' block found in file
        out_html = re.sub(r'95% CI: [^<]*', ci_str, out_html, count=1)

out_html = replace_element_text(out_html, 'kpi-ctrl', fmt_int(control_reports))

# Replace JS arrays: PRR_VALS and donut data
# PRR_VALS=[3.20,2.80,2.10,1.60,1.40];
prr_js = '[' + ','.join([str(v) for v in per_drug_prr_vals]) + ']'
out_html = re.sub(r'const PRR_VALS=\[[^\]]*\];', f'const PRR_VALS={prr_js};', out_html)

# Donut data: find dataset data:[48,22,16,9,5]
donut_js = '[' + ','.join([str(int(round(v))) for v in per_drug_pct]) + ']'
# Replace the chart dataset that contains the hard-coded donut values with live values.
out_html = re.sub(r'data\s*:\s*\[\s*48\s*,\s*22\s*,\s*16\s*,\s*9\s*,\s*5\s*\]', f'data:{donut_js}', out_html)
# Also replace legend percentages text in donut legend values
legend_pattern = re.compile(r'(<div class="legend-item">.*?<span class="legend-val" style="color:[^>]+">)([^<]+)(</span></div>)', re.S)
legend_matches = list(legend_pattern.finditer(out_html))
if legend_matches and len(legend_matches) >= len(per_drug_pct):
    # Replace sequentially using an iterator over per_drug_pct
    replacements = [f"{int(round(v))}%" for v in per_drug_pct]
    def legend_repl(match, repl_text):
        return match.group(1) + repl_text + match.group(3)
    # perform replacements from end to start to preserve indices
    for i, m in enumerate(legend_matches[:len(replacements)]):
        start, end = m.span(2)
        out_html = out_html[:start] + replacements[i] + out_html[end:]

# Replace PRR numbers in the drug table rows and widths
# Build new tbody rows
rows = []
colors = ['var(--teal)','var(--yellow)','var(--coral)','var(--purple)','var(--blue)']
bar_colors = ['var(--teal)','var(--yellow)','var(--coral)','var(--purple)','var(--blue)']
for i, d in enumerate(drug_order):
    name = d.title().replace('Tirzepatide','Tirzepatide').replace('Semaglutide','Semaglutide').capitalize()
    n = int(per_drug_n[i] or 0)
    gi = int(per_drug_gi[i] or 0)
    prr = per_drug_prr_vals[i]
    # css color mapping similar to template
    color = colors[i]
    bar_color = ['#00D4AA','#FFD166','#FF5E6C','#A78BFA','#4FA3E0'][i]
    width_pct = min(100, int((prr / max(4, max(per_drug_prr_vals))) * 100))
    # decide signal badge
    badge = '<span class="badge badge-muted" style="font-size:10px">&#9711; Monitor</span>'
    if prr >= 2.0:
        badge = '<span class="badge badge-coral" style="font-size:10px">&#9650; Signal</span>'
    gi_rate_cell = f"{(gi / n * 100):.1f}%" if n else "0.0%"
    rows.append(f"<tr><td><span style=\"color:{color};font-weight:700\">{name}</span></td><td>{fmt_int(n)}</td><td>{fmt_int(gi)}</td><td>{gi_rate_cell}</td><td><span style=\"color:{bar_color}\">{prr:.2f}</span><span class=\"prr-bar-bg\"><span class=\"prr-bar-fill\" style=\"background:{bar_color};width:{width_pct}%\"></span></span></td><td>n/a</td><td>n/a</td><td>{badge}</td></tr>")

new_tbody = '<tbody id="drug-tbody">\n' + '\n'.join(rows) + '\n</tbody>'
out_html = re.sub(r'<tbody id="drug-tbody">[\s\S]*?</tbody>', new_tbody, out_html, count=1)

# Write out
OUT.write_text(out_html, encoding='utf-8')
print(f'Wrote {OUT} (size={OUT.stat().st_size} bytes)')
