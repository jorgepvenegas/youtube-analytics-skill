# Web Report Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 new data sections to `serve_report.py`, remove hardcoded photography classifiers, and update section ordering per the approved design spec.

**Architecture:** The script is a single file generating inline HTML via Python f-strings. New sections follow the same pattern: load CSV → build Python data structure → render HTML → pass JSON to Chart.js. All new CSVs are optional (guarded with `exists()` checks) so the report still works on older data.

**Tech Stack:** Python 3.13, pandas, numpy (already installed), Chart.js (via CDN, already loaded), vanilla JS for retention dropdown.

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `scripts/serve_report.py` | All changes — new data loading, removals, new HTML sections, new JS |

---

### Task 1: Remove Hardcoded Classifiers

**Files:**
- Modify: `scripts/serve_report.py`

- [ ] **Step 1: Delete `classify_title()` and `classify_format()` functions**

Delete these two functions and all their references. They appear before `duration_bucket()`. Remove:
- The entire `def classify_title(title):` function (12 lines of regex patterns for photography topics)
- The entire `def classify_format(title, duration):` function (10 lines)

- [ ] **Step 2: Remove Topic and Format column assignments**

Find and delete these two lines:
```python
summary['Topic'] = summary['Video title'].apply(classify_title)
summary['Format'] = summary.apply(lambda r: classify_format(r['Video title'], r['Duration (seconds)']), axis=1)
```

- [ ] **Step 3: Verify the file still parses**

```bash
uv run python -c "import scripts.serve_report; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/serve_report.py
git commit -m "refactor: remove hardcoded photography topic/format classifiers"
```

---

### Task 2: Add Optional CSV Loader + Load New Data Files

**Files:**
- Modify: `scripts/serve_report.py`

- [ ] **Step 1: Add `load_optional_csv()` helper after the `summary` loading block**

Add this after the existing CSV loading (around line 30, after the summary loading):

```python
def load_optional_csv(path):
    """Load a CSV if it exists, otherwise return None."""
    if path.exists():
        return pd.read_csv(path)
    return None
```

- [ ] **Step 2: Load all new CSV files after the existing data loading**

Add this block after the existing data loading (after the `summary = summary[summary['Content'] != 'Total'].copy()` block):

```python
# ── Load new expansion CSVs ──────────────────────────────────────────
traffic_df = load_optional_csv(base / "Traffic sources.csv")
search_df = load_optional_csv(base / "Search terms.csv")
geo_df = load_optional_csv(base / "Geography.csv")
device_df = load_optional_csv(base / "Device type.csv")
content_type_df = load_optional_csv(base / "Content type.csv")
demographics_df = load_optional_csv(base / "Demographics.csv")
retention_df = load_optional_csv(base / "Retention.csv")
```

- [ ] **Step 3: Build content-type aggregates for Content Type Breakdown**

Add this **after** the new CSV loads:

```python
# ── Content Type Breakdown aggregates ──────────────────────────────
content_type_agg = None
if content_type_df is not None:
    agg = content_type_df.groupby('Content type').agg(
        Videos=('Video', 'nunique'),
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
        Avg_pct_viewed=('Avg % viewed', 'mean'),
        Subscribers_gained=('Subscribers gained', 'sum'),
    ).reset_index()
    agg.columns = ['Content type', 'Videos', 'Views', 'Watch time (hours)', 'Avg % viewed', 'Subscribers gained']
    agg = agg.sort_values('Views', ascending=False)
    content_type_agg = agg
```

- [ ] **Step 4: Build traffic source aggregates**

Add after the content type block:

```python
# ── Traffic Source aggregates ────────────────────────────────────────
traffic_agg = None
traffic_pct = None
if traffic_df is not None:
    agg = traffic_df.groupby('Traffic source').agg(
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
    ).reset_index()
    agg.columns = ['Traffic source', 'Views', 'Watch time (hours)']
    agg = agg.sort_values('Views', ascending=False)
    total_views = agg['Views'].sum()
    agg['% of Views'] = (agg['Views'] / total_views * 100).round(1)
    traffic_agg = agg
    traffic_pct = {row['Traffic source']: row['% of Views'] for _, row in agg.iterrows()}
```

- [ ] **Step 5: Build per-video top traffic source map**

Add after traffic_agg:

```python
# ── Per-video dominant traffic source ──────────────────────────────
video_top_source = {}
if traffic_df is not None:
    for vid, grp in traffic_df.groupby('Video'):
        top = grp.loc[grp['Views'].idxmax()]
        video_top_source[vid] = top['Traffic source']
```

- [ ] **Step 6: Build geography aggregates (top 10 by views)**

Add after video_top_source:

```python
# ── Geography aggregates ────────────────────────────────────────────
geo_top10 = None
if geo_df is not None:
    agg = geo_df.groupby('Country').agg(
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
        Subscribers_gained=('Subscribers gained', 'sum'),
    ).reset_index()
    agg.columns = ['Country', 'Views', 'Watch time (hours)', 'Subscribers gained']
    agg = agg.sort_values('Views', ascending=False).head(10)
    geo_top10 = agg
```

- [ ] **Step 7: Build device breakdown aggregates**

Add after geo_top10:

```python
# ── Device breakdown aggregates ─────────────────────────────────────
device_agg = None
if device_df is not None:
    agg = device_df.groupby('Device').agg(
        Views=('Views', 'sum'),
        Watch_time=('Watch time (hours)', 'sum'),
    ).reset_index()
    agg.columns = ['Device', 'Views', 'Watch time (hours)']
    agg = agg.sort_values('Views', ascending=False)
    device_agg = agg
```

- [ ] **Step 8: Build demographics aggregates**

Add after device_agg:

```python
# ── Demographics aggregates ─────────────────────────────────────────
demographics_agg = None
if demographics_df is not None:
    agg = demographics_df.groupby(['Age group', 'Gender']).agg(
        Viewer_pct=('Viewer %', 'mean'),
    ).reset_index()
    agg.columns = ['Age group', 'Gender', 'Viewer %']
    demographics_agg = agg.sort_values(['Age group', 'Gender'])
```

- [ ] **Step 9: Build retention data structure**

Add after demographics_agg:

```python
# ── Retention data ──────────────────────────────────────────────────
retention_videos = None
retention_records = None
if retention_df is not None:
    retention_videos = (
        retention_df[['Video', 'Video title']]
        .drop_duplicates('Video')
        .to_dict('records')
    )
    retention_records = df_to_records(retention_df)
```

- [ ] **Step 10: Build search terms table**

Add after retention_records:

```python
# ── Search terms table ─────────────────────────────────────────────
search_table = None
if search_df is not None:
    search_table = search_df.sort_values('Views', ascending=False).reset_index(drop=True)
    search_table.insert(0, '#', search_table.index + 1)
```

- [ ] **Step 11: Build per-video content type map**

Add after search_table:

```python
# ── Per-video content type map ──────────────────────────────────────
video_content_type = {}
if content_type_df is not None:
    # One row per video (videoOnDemand, short, or liveStream)
    for _, row in content_type_df.iterrows():
        video_content_type[row['Video']] = row['Content type']
```

- [ ] **Step 12: Verify the file parses and generates**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest 2>&1 | tail -3
```

Expected: `Report generated: report.html`

- [ ] **Step 13: Commit**

```bash
git add scripts/serve_report.py
git commit -m "data: load all new expansion CSVs and build aggregates"
```

---

### Task 3: Update Top/Bottom + Funnel + Top20% — Remove Topic/Format Columns

**Files:**
- Modify: `scripts/serve_report.py`

- [ ] **Step 1: Update top_cols in top/bottom videos**

Find:
```python
top_cols = ['Video title', 'Views', 'Watch time (hours)', 'Likes', 'Comments added',
            'Shares', 'Net subscribers', 'CTR (%)', 'AVD ratio', 'Engagement rate (%)', 'Topic', 'Format']
```

Replace with:
```python
top_cols = ['Video title', 'Views', 'Watch time (hours)', 'Likes', 'Comments added',
            'Shares', 'Net subscribers', 'CTR (%)', 'AVD ratio', 'Engagement rate (%)']
```

- [ ] **Step 2: Update top10/bottom10 template with content type + top source**

Find the Top 10 table HTML header:
```html
        <th>Topic / Format</th>
      </tr>
    </thead>
    <tbody>
```

Replace with:
```html
        <th>Content type</th>
        <th>Top source</th>
      </tr>
    </thead>
    <tbody>
```

Then find the Top 10 row template and update:

Find:
```python
        <td><span class="topic-tag">{row['Topic']} / {row['Format']}</span></td>
      </tr>
'''

html += '''    </tbody>
  </table>

  <h2>Bottom 10 Videos</h2>
```

Replace with:
```python
        <td>{video_content_type.get(row['Content'], '')}</td>
        <td>{video_top_source.get(row['Content'], '')}</td>
      </tr>
'''

html += '''    </tbody>
  </table>

  <h2>Bottom 10 Videos</h2>
```

Then find the Bottom 10 header and row template:

Find:
```html
        <th>Topic / Format</th>
      </tr>
    </thead>
    <tbody>
```

Replace with:
```html
        <th>Content type</th>
        <th>Top source</th>
      </tr>
    </thead>
    <tbody>
```

And replace the Bottom 10 row:
```python
        <td><span class="topic-tag">{row['Topic']} / {row['Format']}</span></td>
      </tr>
```

With:
```python
        <td>{video_content_type.get(row['Content'], '')}</td>
        <td>{video_top_source.get(row['Content'], '')}</td>
      </tr>
```

- [ ] **Step 3: Update top_vs_bottom (remove topic dicts)**

Find:
```python
    "top_topics": top20['Topic'].value_counts().to_dict(),
    "bottom_topics": bottom20['Topic'].value_counts().to_dict(),
```

Delete both lines.

- [ ] **Step 4: Update funnel_data (remove topic/format)**

Find:
```python
        "topic": row['Topic'],
        "format": row['Format'],
```

Replace with:
```python
        "content_type": video_content_type.get(row['Content'], ''),
        "top_source": video_top_source.get(row['Content'], ''),
```

Also update the funnel HTML template — find the header:
```html
        <th>Topic / Format</th>
```

Replace with:
```html
        <th>Type</th>
        <th>Top source</th>
```

And find the row:
```python
        <td><span class="topic-tag">{v['topic']} / {v['format']}</span></td>
```

Replace with:
```python
        <td>{v['content_type']}</td>
        <td>{v['top_source']}</td>
```

- [ ] **Step 5: Update momentum table (remove Topic column)**

Find the momentum table HTML header:
```html
    <thead><tr><th>Video</th><th class="num">Views</th><th class="num">Age (days)</th><th class="num">Views/Day</th><th>Topic</th></tr></thead>
```

Replace with:
```html
    <thead><tr><th>Video</th><th class="num">Views</th><th class="num">Age (days)</th><th class="num">Views/Day</th></tr></thead>
```

And find the momentum row:
```python
        <td><span class="topic-tag">{row['Topic']}</span></td>
      </tr>
```

Replace with:
```python
      </tr>
```

- [ ] **Step 6: Verify the file parses and generates**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest 2>&1 | tail -3
```

Expected: `Report generated: report.html`

- [ ] **Step 7: Commit**

```bash
git add scripts/serve_report.py
git commit -m "feat: replace Topic/Format columns with content type and top source in all tables"
```

---

### Task 4: Remove Topic/Format Segment Tables and Charts

**Files:**
- Modify: `scripts/serve_report.py`

- [ ] **Step 1: Delete topic_agg and fmt_agg**

Find and delete the entire `topic_agg` block (around 15 lines) and the entire `fmt_agg` block (around 13 lines). They start with:
```python
topic_agg = summary.groupby('Topic').agg({
```
and
```python
fmt_agg = summary.groupby('Format').agg({
```

- [ ] **Step 2: Remove topic/format chart containers from HTML**

Find:
```html
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="topicChart"></canvas>
    </div>
    <div class="chart-container">
      <canvas id="formatChart"></canvas>
    </div>
  </div>
```

Replace with:
```html
```

(i.e., delete the entire block)

- [ ] **Step 3: Remove "Segment Analysis: By Topic" HTML table**

Find and delete the entire `<section>` block containing `<h2>Segment Analysis: By Topic</h2>`.

- [ ] **Step 4: Remove "Segment Analysis: By Format" HTML table**

Find and delete the entire `<section>` block containing `<h2>Segment Analysis: By Format</h2>`.

- [ ] **Step 5: Remove topic/format Chart.js initialization from JS block**

Find and delete the topicChart and formatChart Chart.js initializations in the `<script>` block:
- The `// Topic views bar chart` section (~15 lines)
- The `// Format views bar chart` section (~15 lines)

- [ ] **Step 6: Remove topic_json and format_json from the format() call**

Find:
```python
    topic_json=json.dumps(df_to_records(topic_agg)),
    format_json=json.dumps(df_to_records(fmt_agg)),
```

Delete both lines.

- [ ] **Step 7: Verify the file parses and generates**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest 2>&1 | tail -3
```

Expected: `Report generated: report.html`

- [ ] **Step 8: Commit**

```bash
git add scripts/serve_report.py
git commit -m "feat: remove hardcoded topic/format segment tables and charts"
```

---

### Task 5: Add New HTML Sections

**Files:**
- Modify: `scripts/serve_report.py`

- [ ] **Step 1: Add Content Type Breakdown section after Channel Snapshot**

Find the line:
```python
html += '''</section>
```

that closes the Channel Snapshot section (the one with `kpi-grid`).

Add the following **after** that `</section>` closing block:

```python
# ── Content Type Breakdown ──────────────────────────────────────────
if content_type_agg is not None:
    content_type_json = json.dumps(df_to_records(content_type_agg))
    html += f'''
<section>
  <h2>Content Type Breakdown</h2>
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="contentTypeChart"></canvas>
    </div>
    <div class="chart-container" style="overflow: auto;">
      <table>
        <thead>
          <tr>
            <th>Content type</th>
            <th class="num">Videos</th>
            <th class="num">Views</th>
            <th class="num">WT (h)</th>
            <th class="num">Avg % Viewed</th>
            <th class="num">Subs gained</th>
          </tr>
        </thead>
        <tbody>
'''
    for _, row in content_type_agg.iterrows():
        html += f'''          <tr>
            <td>{row['Content type']}</td>
            <td class="num">{int(row['Videos'])}</td>
            <td class="num">{int(row['Views']):,}</td>
            <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
            <td class="num">{safe_round(row['Avg % viewed'], 1)}%</td>
            <td class="num">{int(row['Subscribers gained']):+}</td>
          </tr>
'''
    html += '''        </tbody>
      </table>
    </div>
  </div>
</section>
'''
```

Note: Set `content_type_json` in the outer scope before the f-string so it's available in the JS block later. Add this at the end of the data building section (before `html = f'''`):

```python
content_type_json = json.dumps(df_to_records(content_type_agg)) if content_type_agg is not None else '[]'
```

- [ ] **Step 2: Add Traffic Sources section**

Add after the Content Type Breakdown section (after its `</section>` closing `'''`):

```python
# ── Traffic Sources ────────────────────────────────────────────────
if traffic_agg is not None:
    traffic_json = json.dumps(df_to_records(traffic_agg))
    traffic_label_json = json.dumps(list(traffic_agg['Traffic source']))
    traffic_views_json = json.dumps(list(traffic_agg['Views']))
    html += f'''
<section>
  <h2>Traffic Sources</h2>
  <div class="chart-row">
    <div class="chart-container">
      <canvas id="trafficDonutChart"></canvas>
    </div>
    <div class="chart-container" style="overflow: auto;">
      <table>
        <thead>
          <tr>
            <th>Traffic source</th>
            <th class="num">Views</th>
            <th class="num">WT (h)</th>
            <th class="num">% of Views</th>
          </tr>
        </thead>
        <tbody>
'''
    for _, row in traffic_agg.iterrows():
        html += f'''          <tr>
            <td>{row['Traffic source']}</td>
            <td class="num">{int(row['Views']):,}</td>
            <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
            <td class="num">{row['% of Views']}%</td>
          </tr>
'''
    html += '''        </tbody>
      </table>
    </div>
  </div>
</section>
'''
```

Set these vars in the outer scope:
```python
traffic_label_json = json.dumps(list(traffic_agg['Traffic source'])) if traffic_agg is not None else '[]'
traffic_views_json = json.dumps(list(traffic_agg['Views'])) if traffic_agg is not None else '[]'
```

- [ ] **Step 3: Add Search Terms section**

Add after Traffic Sources:

```python
# ── Search Terms ────────────────────────────────────────────────────
if search_table is not None:
    search_json = json.dumps(df_to_records(search_table))
    html += '''
<section>
  <h2>Top Search Terms</h2>
  <table>
    <thead>
      <tr>
        <th class="num">#</th>
        <th>Search term</th>
        <th>Video</th>
        <th class="num">Views</th>
        <th class="num">WT (h)</th>
      </tr>
    </thead>
    <tbody>
'''
    for _, row in search_table.iterrows():
        html += f'''      <tr>
        <td class="num">{int(row['#'])}</td>
        <td style="font-weight: 600;">{row['Search term']}</td>
        <td style="color: var(--text-dim); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{row['Video title'][:55]}</td>
        <td class="num">{int(row['Views']):,}</td>
        <td class="num">{safe_round(row['Watch time (hours)'], 1)}</td>
      </tr>
'''
    html += '''    </tbody>
  </table>
</section>
'''
```

Set `search_json` in outer scope:
```python
search_json = json.dumps(df_to_records(search_table)) if search_table is not None else '[]'
```

- [ ] **Step 4: Add Geography + Device Breakdown (side by side)**

Add after Search Terms. Note: these go in the same section (side by side in a chart-row grid):

```python
# ── Geography + Device Breakdown ────────────────────────────────────
if geo_top10 is not None or device_agg is not None:
    geo_label_json = json.dumps(list(geo_top10['Country'])) if geo_top10 is not None else '[]'
    geo_views_json = json.dumps(list(geo_top10['Views'])) if geo_top10 is not None else '[]'
    device_label_json = json.dumps(list(device_agg['Device'])) if device_agg is not None else '[]'
    device_views_json = json.dumps(list(device_agg['Views'])) if device_agg is not None else '[]'

    html += f'''
<section>
  <h2>Audience Insights</h2>
  <div class="chart-row">
'''
    if geo_top10 is not None:
        html += f'''    <div class="chart-container">
      <canvas id="geoChart"></canvas>
    </div>
'''
    if device_agg is not None:
        html += f'''    <div class="chart-container">
      <canvas id="deviceChart"></canvas>
    </div>
'''
    html += '''  </div>
</section>
'''
```

Set in outer scope:
```python
geo_label_json = json.dumps(list(geo_top10['Country'])) if geo_top10 is not None else '[]'
geo_views_json = json.dumps(list(geo_top10['Views'])) if geo_top10 is not None else '[]'
device_label_json = json.dumps(list(device_agg['Device'])) if device_agg is not None else '[]'
device_views_json = json.dumps(list(device_agg['Views'])) if device_agg is not None else '[]'
```

- [ ] **Step 5: Add Demographics section**

Add after Geography/Device:

```python
# ── Demographics ───────────────────────────────────────────────────
if demographics_agg is not None:
    demo_json = json.dumps(df_to_records(demographics_agg))
    html += f'''
<section>
  <h2>Demographics</h2>
  <div class="chart-container" style="max-width: 600px;">
    <canvas id="demoChart"></canvas>
  </div>
</section>
'''
```

Set in outer scope:
```python
demo_json = json.dumps(df_to_records(demographics_agg)) if demographics_agg is not None else '[]'
```

- [ ] **Step 6: Add Retention Curves section**

Add after Demographics:

```python
# ── Retention Curves ────────────────────────────────────────────────
if retention_df is not None:
    retention_json = json.dumps(retention_records)
    default_video_id = retention_videos[0]['Video'] if retention_videos else ''
    default_video_title = retention_videos[0]['Video title'] if retention_videos else ''

    html += f'''
<section>
  <h2>Retention Curves</h2>
  <div class="chart-container">
    <div style="margin-bottom: 1rem;">
      <label for="retentionSelect" style="color: var(--text-dim); font-size: 0.85rem; margin-right: 0.5rem;">Video:</label>
      <select id="retentionSelect" onchange="updateRetentionChart(this.value)" style="background: var(--card); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 1rem; min-width: 320px;">
'''
    for v in retention_videos:
        sel = 'selected' if v['Video'] == default_video_id else ''
        html += f'''        <option value="{v['Video']}" {sel}>{v['Video title'][:70]}</option>
'''
    html += '''      </select>
    </div>
    <canvas id="retentionChart"></canvas>
  </div>
</section>
'''
```

Set in outer scope:
```python
retention_json = json.dumps(retention_records) if retention_records is not None else '[]'
default_video_id = retention_videos[0]['Video'] if retention_videos else ''
```

- [ ] **Step 7: Verify the file parses and generates**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest 2>&1 | tail -3
```

Expected: `Report generated: report.html`

- [ ] **Step 8: Commit**

```bash
git add scripts/serve_report.py
git commit -m "feat: add new HTML sections for all expansion datasets"
```

---

### Task 6: Add All New Chart.js Initialization

**Files:**
- Modify: `scripts/serve_report.py`

- [ ] **Step 1: Add content type chart**

In the `<script>` block, add after the viewsChart initialization:

```javascript
// Content type bar chart
if (contentTypeChartData.length > 0) {
  new Chart(document.getElementById('contentTypeChart'), {
    type: 'bar',
    data: {
      labels: contentTypeChartData.map(d => d['Content type']),
      datasets: [{
        label: 'Views',
        data: contentTypeChartData.map(d => d['Views']),
        backgroundColor: '#ff6b35',
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      plugins: { title: { display: true, text: 'Views by Content Type', color: '#e0e0e0' } },
      scales: { y: { beginAtZero: true } }
    }
  });
}
```

- [ ] **Step 2: Add traffic donut chart**

Add after the content type chart:

```javascript
// Traffic sources donut chart
if (trafficChartData.length > 0) {
  new Chart(document.getElementById('trafficDonutChart'), {
    type: 'doughnut',
    data: {
      labels: trafficChartData.map(d => d['Traffic source']),
      datasets: [{
        data: trafficChartData.map(d => d['Views']),
        backgroundColor: ['#ff6b35','#00d4aa','#f0c040','#6c5ce7','#e056a0','#888','#a29bfe','#fd79a8'],
        borderWidth: 0,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        title: { display: true, text: 'Traffic Source Mix', color: '#e0e0e0' },
        legend: { position: 'bottom', labels: { color: '#8888aa', padding: 12 } }
      }
    }
  });
}
```

- [ ] **Step 3: Add geography horizontal bar chart**

Add after traffic donut:

```javascript
// Geography horizontal bar chart
if (geoChartData.length > 0) {
  new Chart(document.getElementById('geoChart'), {
    type: 'bar',
    data: {
      labels: geoChartData.map(d => d['Country']),
      datasets: [{
        label: 'Views',
        data: geoChartData.map(d => d['Views']),
        backgroundColor: '#00d4aa',
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { title: { display: true, text: 'Top Countries by Views', color: '#e0e0e0' } },
      scales: { x: { beginAtZero: true } }
    }
  });
}
```

- [ ] **Step 4: Add device donut chart**

Add after geo chart:

```javascript
// Device breakdown donut chart
if (deviceChartData.length > 0) {
  new Chart(document.getElementById('deviceChart'), {
    type: 'doughnut',
    data: {
      labels: deviceChartData.map(d => d['Device']),
      datasets: [{
        data: deviceChartData.map(d => d['Views']),
        backgroundColor: ['#ff6b35','#00d4aa','#f0c040','#6c5ce7'],
        borderWidth: 0,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        title: { display: true, text: 'Device Breakdown', color: '#e0e0e0' },
        legend: { position: 'bottom', labels: { color: '#8888aa', padding: 12 } }
      }
    }
  });
}
```

- [ ] **Step 5: Add demographics stacked bar chart**

Add after device chart:

```javascript
// Demographics stacked bar chart
if (demoChartData.length > 0) {
  const ages = [...new Set(demoChartData.map(d => d['Age group']))];
  const genders = [...new Set(demoChartData.map(d => d['Gender']))];
  const genderColors = { 'male': '#ff6b35', 'female': '#00d4aa', 'user_specified': '#f0c040' };
  new Chart(document.getElementById('demoChart'), {
    type: 'bar',
    data: {
      labels: ages,
      datasets: genders.map(g => ({
        label: g,
        data: ages.map(a => {
          const row = demoChartData.find(d => d['Age group'] === a && d['Gender'] === g);
          return row ? row['Viewer %'] : 0;
        }),
        backgroundColor: genderColors[g] || '#888',
      }))
    },
    options: {
      responsive: true,
      plugins: {
        title: { display: true, text: 'Audience Demographics by Age & Gender', color: '#e0e0e0' },
        legend: { position: 'bottom', labels: { color: '#8888aa', padding: 12 } }
      },
      scales: {
        x: { stacked: true },
        y: { stacked: true, beginAtZero: true, max: 100, title: { display: true, text: 'Viewer %', color: '#8888aa' } }
      }
    }
  });
}
```

- [ ] **Step 6: Add retention line chart + updateRetentionChart function**

Add after demographics chart:

```javascript
// Retention curve chart
if (retentionChartData.length > 0) {
  const defaultVid = retentionChartData[0] && retentionChartData[0]['Video'];
  let retChart = null;
  function updateRetentionChart(videoId) {
    const rows = retentionChartData.filter(d => d['Video'] === videoId);
    if (!rows.length) return;
    const labels = rows.map(d => (d['Elapsed ratio'] * 100).toFixed(0) + '%');
    const watchRatio = rows.map(d => d['Audience watch ratio']);
    const relRet = rows.map(d => d['Relative retention']);
    if (!retChart) {
      retChart = new Chart(document.getElementById('retentionChart'), {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Watch ratio',
              data: watchRatio,
              borderColor: '#ff6b35',
              backgroundColor: 'rgba(255,107,53,0.1)',
              fill: false,
              tension: 0.3,
              pointRadius: 3,
            },
            {
              label: 'Relative retention',
              data: relRet,
              borderColor: '#00d4aa',
              borderDash: [6, 4],
              fill: false,
              tension: 0.3,
              pointRadius: 2,
            }
          ]
        },
        options: {
          responsive: true,
          plugins: {
            title: { display: true, text: 'Audience Retention', color: '#e0e0e0' },
            legend: { position: 'bottom', labels: { color: '#8888aa', padding: 12 } }
          },
          scales: {
            x: { title: { display: true, text: '% of Video', color: '#8888aa' } },
            y: { beginAtZero: true, title: { display: true, text: 'Retention Ratio', color: '#8888aa' } }
          }
        }
      });
    } else {
      retChart.data.labels = labels;
      retChart.data.datasets[0].data = watchRatio;
      retChart.data.datasets[1].data = relRet;
      retChart.update();
    }
  }
  if (defaultVid) updateRetentionChart(defaultVid);
}
```

- [ ] **Step 7: Update the format() call to include all new JSON variables**

Find the `.format()` call at the end of the HTML generation and add all new variables:

```python
).format(
    base_name=base.name,
    funnel_json=json.dumps(funnel_data),
    corr_json=json.dumps(correlations),
    trend_json=json.dumps(trend_data),
    content_type_json=content_type_json,
    traffic_json=traffic_json,
    search_json=search_json,
    demo_json=demo_json,
    retention_json=retention_json,
    geo_label_json=geo_label_json,
    geo_views_json=geo_views_json,
    device_label_json=device_label_json,
    device_views_json=device_views_json,
)
```

- [ ] **Step 8: Update the JS data declarations**

In the `<script>` block, find the existing declarations:

```javascript
const topicData = {topic_json};
const formatData = {format_json};
const funnelData = {funnel_json};
const corrData = {corr_json};
const trendData = {trend_json};
```

Replace with:

```javascript
const funnelData = {funnel_json};
const corrData = {corr_json};
const trendData = {trend_json};

// New expansion data
const contentTypeChartData = {content_type_json};
const trafficChartData = {traffic_json};
const searchChartData = {search_json};
const demoChartData = {demo_json};
const retentionChartData = {retention_json};
const geoChartData = {geo_label_json}.map((label, i) => ({{'Country': label, 'Views': {geo_views_json}[i]}}));
const deviceChartData = {device_label_json}.map((label, i) => ({{'Device': label, 'Views': {device_views_json}[i]}}));
```

Note: `geoChartData` and `deviceChartData` are reconstructed from label and views arrays. Use `[]` for empty cases.

- [ ] **Step 9: Verify the file parses and generates**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest 2>&1 | tail -3
```

Expected: `Report generated: report.html`

- [ ] **Step 10: Commit**

```bash
git add scripts/serve_report.py
git commit -m "feat: add Chart.js initializations for all new sections"
```

---

### Task 7: Smoke Test the Report

- [ ] **Step 1: Generate the report**

```bash
uv run python scripts/serve_report.py --no-serve --data-dir data/latest 2>&1
```

- [ ] **Step 2: Verify all new sections appear in the HTML**

```bash
grep -E 'Content Type Breakdown|Traffic Sources|Top Search Terms|Audience Insights|Demographics|Retention Curves' report.html
```

Expected: 6 matches — one per new section.

- [ ] **Step 3: Verify removed sections are gone**

```bash
grep -c 'Segment Analysis: By Topic\|Segment Analysis: By Format\|classify_title\|classify_format' report.html
```

Expected: `0`

- [ ] **Step 4: Verify no Python errors**

```bash
uv run python -m pytest tests/ -v 2>&1 | tail -3
```

Expected: All tests PASS (existing tests — no new test files needed for HTML generation)

- [ ] **Step 5: Open in browser for manual verification**

```bash
uv run python scripts/serve_report.py --no-serve
```

Then open `report.html` in a browser. Check:
- Channel Snapshot is first section
- Content Type Breakdown has a bar chart + table
- Traffic Sources has a donut chart + table
- Search Terms table renders
- Audience Insights shows Geography + Device side by side
- Demographics stacked bar renders (if data present)
- Retention Curves dropdown + line chart renders (if data present)
- Top/Bottom tables have "Content type" and "Top source" columns
- No Topic or Format columns anywhere

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: web report expansion complete — all new data sections"
```
