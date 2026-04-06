const elements = {
  searchForm: document.querySelector("#search-form"),
  profileForm: document.querySelector("#profile-form"),
  queryInput: document.querySelector("#query-input"),
  userIdInput: document.querySelector("#user-id-input"),
  displayNameInput: document.querySelector("#display-name-input"),
  homeButton: document.querySelector("#home-button"),
  refreshButton: document.querySelector("#refresh-button"),
  digestTitle: document.querySelector("#digest-title"),
  digestList: document.querySelector("#digest-list"),
  feedTitle: document.querySelector("#feed-title"),
  feedMeta: document.querySelector("#feed-meta"),
  cardsContainer: document.querySelector("#cards-container"),
  sourceBreakdown: document.querySelector("#source-breakdown"),
  profileSummary: document.querySelector("#profile-summary"),
  entitySummary: document.querySelector("#entity-summary"),
  sourceHealthMeta: document.querySelector("#source-health-meta"),
  sourceHealthSummary: document.querySelector("#source-health-summary"),
  sourceHealthRollups: document.querySelector("#source-health-rollups"),
  sourceHealthRuns: document.querySelector("#source-health-runs"),
  sourceHealthModal: document.querySelector("#source-health-modal"),
  sourceHealthModalTitle: document.querySelector("#source-health-modal-title"),
  sourceHealthModalMeta: document.querySelector("#source-health-modal-meta"),
  sourceHealthModalStatus: document.querySelector("#source-health-modal-status"),
  sourceHealthModalList: document.querySelector("#source-health-modal-list"),
  sourceHealthModalClose: document.querySelector("#source-health-modal-close"),
  statusBanner: document.querySelector("#status-banner"),
  articleTemplate: document.querySelector("#article-card-template"),
  clusterDetailModal: document.querySelector("#cluster-detail-modal"),
  clusterDetailTitle: document.querySelector("#cluster-detail-title"),
  clusterDetailMeta: document.querySelector("#cluster-detail-meta"),
  clusterDetailControls: document.querySelector("#cluster-detail-controls"),
  clusterDetailStatus: document.querySelector("#cluster-detail-status"),
  clusterDetailSources: document.querySelector("#cluster-detail-sources"),
  clusterDetailList: document.querySelector("#cluster-detail-list"),
  clusterDetailClose: document.querySelector("#cluster-detail-close"),
};

const PROFILE_STORAGE_KEY = "acg-search-sg-profile";

const state = {
  currentMode: "home",
  currentQuery: "",
  currentItems: [],
  currentGroups: [],
  searchDigestRequestId: 0,
  userId: "",
  displayName: "",
  profile: null,
  pinnedEntities: [],
  clusterDetailEntity: "",
  clusterDetailRequestId: 0,
  sourceHealthSelectedSource: "",
  sourceHealthRollupItems: [],
  sourceHealthModalSource: "",
  sourceHealthModalRequestId: 0,
  suppressModalRouteSync: false,
  pendingModalRouteMode: "push",
};

function createEntityButton(entityName, className = "chip entity-chip entity-filter-button") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.dataset.entityName = entityName;
  button.textContent = entityName;
  return button;
}

function uniqueValues(values) {
  return [...new Set((values || []).filter((value) => value && value.trim()))];
}

function entityPreferenceInputs() {
  return [...document.querySelectorAll('input[data-preference="entity"]')];
}

function syncPinnedEntityCheckboxes() {
  const pinned = new Set(state.pinnedEntities || []);
  entityPreferenceInputs().forEach((input) => {
    input.checked = pinned.has(input.value);
  });
}

function isPinnedEntity(entityName) {
  return (state.pinnedEntities || []).includes(entityName);
}

function createEntityFollowButton(entityName, className = "entity-follow-button") {
  const following = isPinnedEntity(entityName);
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.dataset.entityName = entityName;
  button.dataset.following = String(following);
  button.setAttribute("aria-pressed", String(following));
  button.textContent = following ? "Following" : "Follow";
  return button;
}

function createEntityDetailButton(entityName, className = "entity-detail-button", label = "Details") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.dataset.entityName = entityName;
  button.textContent = label;
  return button;
}

function createEntityActionGroup(
  entityName,
  {
    focusClassName = "chip entity-chip entity-filter-button",
    focusLabel = entityName,
    followClassName = "entity-follow-button",
    includeDetail = false,
    detailClassName = "entity-detail-button",
    detailLabel = "Details",
  } = {},
) {
  const group = document.createElement("div");
  group.className = "entity-action-group";

  const focusButton = createEntityButton(entityName, focusClassName);
  focusButton.textContent = focusLabel;

  group.append(focusButton);
  if (includeDetail) {
    group.append(createEntityDetailButton(entityName, detailClassName, detailLabel));
  }
  group.append(createEntityFollowButton(entityName, followClassName));
  return group;
}

function applyProfileState(profile) {
  state.profile = profile;
  state.pinnedEntities = uniqueValues(profile?.pinned_entities || state.pinnedEntities);
  syncPinnedEntityCheckboxes();
  renderProfileSummary(profile);
  if (elements.clusterDetailModal?.open && state.clusterDetailEntity) {
    renderClusterDetailControls(state.clusterDetailEntity);
  }
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.json();
}

function setStatus(message, isError = false) {
  elements.statusBanner.textContent = message;
  elements.statusBanner.classList.toggle("error", isError);
}

function relativeTime(value) {
  const publishedAt = new Date(value);
  const minutes = Math.round((publishedAt.getTime() - Date.now()) / 60000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (Math.abs(minutes) < 60) {
    return formatter.format(minutes, "minute");
  }
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 48) {
    return formatter.format(hours, "hour");
  }
  const days = Math.round(hours / 24);
  return formatter.format(days, "day");
}

function compactRequestId(value) {
  if (!value) {
    return "";
  }
  return value.length > 18 ? `${value.slice(0, 18)}...` : value;
}

function healthTone(item) {
  if (item.status === "error") {
    return "error";
  }
  if (item.stale) {
    return "stale";
  }
  return "ok";
}

function healthLabel(item) {
  const tone = healthTone(item);
  if (tone === "error") {
    return "Failing";
  }
  if (tone === "stale") {
    return "Stale";
  }
  return "Healthy";
}

function createGuestId() {
  return `fan-${Math.random().toString(36).slice(2, 8)}`;
}

function readStoredProfile() {
  try {
    return JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function checkedValues(group) {
  return [...document.querySelectorAll(`input[data-preference="${group}"]:checked`)].map((input) => input.value);
}

function writeStoredProfile() {
  localStorage.setItem(
    PROFILE_STORAGE_KEY,
    JSON.stringify({
      userId: state.userId,
      displayName: state.displayName,
      pinnedCategories: checkedValues("category"),
      pinnedEntities: state.pinnedEntities,
      pinnedRegions: checkedValues("region"),
    }),
  );
}

function hydrateProfileForm() {
  const stored = readStoredProfile();
  state.userId = (stored.userId || createGuestId()).toLowerCase();
  state.displayName = stored.displayName || "SG fan";
  state.pinnedEntities = uniqueValues(stored.pinnedEntities || []);

  elements.userIdInput.value = state.userId;
  elements.displayNameInput.value = state.displayName;

  document.querySelectorAll("input[data-preference]").forEach((input) => {
    const values =
      input.dataset.preference === "region"
        ? stored.pinnedRegions || []
        : input.dataset.preference === "entity"
          ? state.pinnedEntities
          : stored.pinnedCategories || [];
    input.checked = values.includes(input.value);
  });
}

function buildProfilePayload() {
  state.userId = (elements.userIdInput.value.trim().toLowerCase() || createGuestId()).slice(0, 64);
  state.displayName = elements.displayNameInput.value.trim();
  elements.userIdInput.value = state.userId;

  const presetEntityValues = new Set(entityPreferenceInputs().map((input) => input.value));
  state.pinnedEntities = uniqueValues([
    ...checkedValues("entity"),
    ...state.pinnedEntities.filter((entityName) => !presetEntityValues.has(entityName)),
  ]);

  return {
    user_id: state.userId,
    display_name: state.displayName || null,
    pinned_categories: checkedValues("category"),
    pinned_tags: [],
    pinned_entities: state.pinnedEntities,
    pinned_regions: checkedValues("region"),
  };
}

function currentRouteQuery() {
  return state.currentMode === "search" && state.currentQuery ? state.currentQuery : "";
}

function currentRouteEntity() {
  return elements.clusterDetailModal?.open && state.clusterDetailEntity ? state.clusterDetailEntity : "";
}

function readRouteState() {
  const params = new URLSearchParams(window.location.search);
  return {
    query: params.get("query")?.trim() || "",
    entity: params.get("entity")?.trim() || "",
  };
}

function writeRouteState({ query = currentRouteQuery(), entity = currentRouteEntity() } = {}, options = {}) {
  const { mode = "replace" } = options;
  const url = new URL(window.location.href);
  if (query) {
    url.searchParams.set("query", query);
  } else {
    url.searchParams.delete("query");
  }

  if (entity) {
    url.searchParams.set("entity", entity);
  } else {
    url.searchParams.delete("entity");
  }

  const nextUrl = `${url.pathname}${url.search}${url.hash}`;
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (nextUrl !== currentUrl) {
    const historyState = { query: query || null, entity: entity || null };
    if (mode === "push") {
      window.history.pushState(historyState, "", nextUrl);
    } else {
      window.history.replaceState(historyState, "", nextUrl);
    }
  }
}

function isExternalArticleHref(href) {
  if (!href) {
    return false;
  }

  try {
    const url = new URL(href);
    if (!["http:", "https:"].includes(url.protocol)) {
      return false;
    }
    return url.origin !== window.location.origin;
  } catch {
    return false;
  }
}

function resultTypeValue(item) {
  if (item?.result_type === "source_page" || item?.source_type === "curated") {
    return "source_page";
  }
  if (item?.result_type === "event" || item?.source_type === "event_listing") {
    return "event";
  }
  return "article";
}

function resultTypeLabel(item) {
  const resultType = resultTypeValue(item);
  if (resultType === "source_page") {
    return "Source page";
  }
  if (resultType === "event") {
    return "Event";
  }
  return "Story";
}

function decorateResultTypePill(pill, item) {
  if (!pill) {
    return;
  }
  const resultType = resultTypeValue(item);
  pill.dataset.resultType = resultType;
  pill.textContent = resultTypeLabel(item);
}

function resolveArticleHref(item) {
  if (resultTypeValue(item) === "event" && isExternalArticleHref(item.event_metadata?.ticket_url)) {
    return item.event_metadata.ticket_url;
  }
  if (isExternalArticleHref(item.url)) {
    return item.url;
  }
  return "";
}

function configureArticleLink(link, item, label = "") {
  const href = resolveArticleHref(item);
  link.dataset.articleId = item.id;

  if (href) {
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.dataset.linkDisabled = "false";
    link.removeAttribute("aria-disabled");
    link.classList.remove("disabled-link");
  } else {
    link.href = "#";
    link.target = "_self";
    link.removeAttribute("rel");
    link.dataset.linkDisabled = "true";
    link.setAttribute("aria-disabled", "true");
    link.classList.add("disabled-link");
  }

  if (label) {
    link.textContent = label;
  }
}

function articleLinkLabel(item) {
  const href = resolveArticleHref(item);
  if (!href) {
    return "Source unavailable";
  }
  const resultType = resultTypeValue(item);
  if (resultType === "source_page") {
    return "Open source";
  }
  if (resultType === "event" && isExternalArticleHref(item.event_metadata?.ticket_url)) {
    return "Open tickets";
  }
  if (resultType === "event") {
    return "Open event";
  }
  return "Open story";
}

function groupFeedEntries(items, groups) {
  const groupMap = new Map((groups || []).map((group) => [group.name, group]));
  const collapsibleEntities = new Set((groups || []).filter((group) => group.count >= 2).map((group) => group.name));
  const consumedItemIds = new Set();
  const emittedEntities = new Set();
  const entries = [];

  items.forEach((item) => {
    if (consumedItemIds.has(item.id)) {
      return;
    }

    const clusterEntity = (item.entity_tags || []).find(
      (entityName) => collapsibleEntities.has(entityName) && !emittedEntities.has(entityName),
    );
    if (!clusterEntity) {
      consumedItemIds.add(item.id);
      entries.push({ type: "article", item });
      return;
    }

    const groupedItems = items.filter((candidate) => (candidate.entity_tags || []).includes(clusterEntity));
    groupedItems.forEach((candidate) => consumedItemIds.add(candidate.id));
    emittedEntities.add(clusterEntity);
    entries.push({
      type: "cluster",
      entityName: clusterEntity,
      group: groupMap.get(clusterEntity),
      items: groupedItems,
      leadItem: groupedItems[0],
    });
  });

  return entries;
}

function renderChips(container, values, className = "chip") {
  container.replaceChildren();
  values.forEach((value) => {
    const chip = document.createElement("span");
    chip.className = className;
    chip.textContent = value;
    container.appendChild(chip);
  });
}

function renderEntityButtons(container, values) {
  container.replaceChildren();
  values.forEach((value) => {
    container.appendChild(createEntityActionGroup(value));
  });
}

function currentEntityItems(entityName) {
  return (state.currentItems || []).filter((item) => (item.entity_tags || []).includes(entityName));
}

function currentEntityGroup(entityName) {
  return (state.currentGroups || []).find((group) => group.name === entityName) || null;
}

function buildEntityGroupSnapshot(entityName, items, existingGroup = null) {
  if (existingGroup) {
    return existingGroup;
  }
  const sourceNames = uniqueValues((items || []).map((item) => item.source_name));
  return {
    name: entityName,
    kind: "topic",
    count: items.length,
    source_count: sourceNames.length,
    headline: items[0]?.title || entityName,
    source_names: sourceNames,
  };
}

function renderDigest(items, title) {
  elements.digestTitle.textContent = title;
  elements.digestList.replaceChildren();
  items.forEach((item) => {
    const listItem = document.createElement("li");
    listItem.textContent = item;
    elements.digestList.appendChild(listItem);
  });
}

function cancelPendingSearchDigest() {
  state.searchDigestRequestId += 1;
}

async function loadDeferredSearchDigest(query, items) {
  const articleIds = (items || [])
    .map((item) => item.id)
    .filter((value) => typeof value === "string" && value)
    .slice(0, 12);

  const requestId = ++state.searchDigestRequestId;
  if (!articleIds.length) {
    renderDigest([], "Why these headlines");
    return;
  }

  renderDigest(["Generating a quick rationale..."], "Why these headlines");

  try {
    const payload = await apiRequest("/api/search/digest", {
      method: "POST",
      body: JSON.stringify({ query, article_ids: articleIds }),
    });
    if (requestId !== state.searchDigestRequestId || state.currentMode !== "search" || state.currentQuery !== query) {
      return;
    }
    renderDigest(payload.digest || [], "Why these headlines");
  } catch (error) {
    if (requestId !== state.searchDigestRequestId || state.currentMode !== "search" || state.currentQuery !== query) {
      return;
    }
    console.error(error);
    renderDigest([], "Why these headlines");
  }
}

function renderSourceBreakdown(sourceBreakdown) {
  elements.sourceBreakdown.replaceChildren();
  Object.entries(sourceBreakdown).forEach(([sourceName, count]) => {
    const chip = document.createElement("span");
    chip.className = "source-chip";
    chip.textContent = `${sourceName} · ${count}`;
    elements.sourceBreakdown.appendChild(chip);
  });
}

function createHealthMetricChip(label, count, tone) {
  const chip = document.createElement("span");
  chip.className = `health-metric-chip ${tone}`;
  chip.textContent = `${label} ${count}`;
  return chip;
}

function percentageLabel(value) {
  return `${Math.round((value || 0) * 100)}%`;
}

function createSourceHealthSparkline(statuses) {
  const row = document.createElement("div");
  row.className = "source-health-sparkline";

  [...(statuses || [])].reverse().forEach((status) => {
    const dot = document.createElement("span");
    dot.className = `source-health-sparkline-dot ${status}`;
    row.appendChild(dot);
  });

  return row;
}

function summarizeSourceRuns(runs) {
  const totalRuns = (runs || []).length;
  const failingRuns = (runs || []).filter((run) => run.status === "error").length;
  const healthyRuns = totalRuns - failingRuns;
  const latestRun = runs?.[0] || null;
  return {
    totalRuns,
    failingRuns,
    healthyRuns,
    failureRate: totalRuns ? failingRuns / totalRuns : 0,
    latestRun,
  };
}

function renderSourceHealth(summary, rollups, runs) {
  const items = summary.items || [];
  state.sourceHealthRollupItems = rollups.items || [];
  elements.sourceHealthSummary.replaceChildren();
  elements.sourceHealthRollups.replaceChildren();
  elements.sourceHealthRuns.replaceChildren();
  elements.sourceHealthMeta.textContent = items.length
    ? `${items.length} tracked sources · updated ${relativeTime(summary.generated_at)}`
    : "No tracked sources yet.";

  const metrics = document.createElement("div");
  metrics.className = "source-health-metrics";
  metrics.append(
    createHealthMetricChip("Healthy", summary.healthy_count || 0, "ok"),
    createHealthMetricChip("Failing", summary.failing_count || 0, "error"),
    createHealthMetricChip("Stale", summary.stale_count || 0, "stale"),
  );
  elements.sourceHealthSummary.appendChild(metrics);

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "profile-empty";
    empty.textContent = "Source health appears here after the first live ingest run.";
    elements.sourceHealthSummary.appendChild(empty);
  } else {
    const attentionItems = items.filter((item) => item.status === "error" || item.stale);
    const displayedItems = (attentionItems.length ? attentionItems : items).slice(0, 4);

    if (!attentionItems.length) {
      const healthy = document.createElement("p");
      healthy.className = "profile-empty";
      healthy.textContent = "All tracked sources look healthy right now.";
      elements.sourceHealthSummary.appendChild(healthy);
    }

    displayedItems.forEach((item) => {
      const card = document.createElement("article");
      const tone = healthTone(item);
      card.className = `source-health-card ${tone}`;

      const heading = document.createElement("div");
      heading.className = "source-health-heading";

      const name = document.createElement("p");
      name.className = "source-health-name";
      name.textContent = item.source_name;

      const badge = document.createElement("span");
      badge.className = `health-badge ${tone}`;
      badge.textContent = healthLabel(item);

      heading.append(name, badge);

      const detail = document.createElement("p");
      detail.className = "source-health-detail";
      detail.textContent = `Fetched ${item.fetched_count} · Stored ${item.persisted_count} · Failures ${item.consecutive_failures}`;

      const context = document.createElement("p");
      context.className = "source-health-context";
      context.textContent = item.last_error
        ? item.last_error
        : item.last_success_at
          ? `Last success ${relativeTime(item.last_success_at)}`
          : `Last run ${relativeTime(item.last_run_at)}`;

      card.append(heading, detail, context);
      elements.sourceHealthSummary.appendChild(card);
    });
  }

  const rollupsHead = document.createElement("p");
  rollupsHead.className = "profile-meta";
  rollupsHead.textContent = `Failure rate over ${rollups.window_hours || 24}h`;
  elements.sourceHealthRollups.appendChild(rollupsHead);

  if (!(rollups.items || []).length) {
    const emptyRollups = document.createElement("p");
    emptyRollups.className = "profile-empty";
    emptyRollups.textContent = "Rollups will appear after more ingest history accumulates.";
    elements.sourceHealthRollups.appendChild(emptyRollups);
  } else {
    rollups.items.forEach((rollup) => {
      const card = document.createElement("article");
      card.className = `source-health-rollup-card ${rollup.latest_status}${state.sourceHealthSelectedSource === rollup.source_name ? " active" : ""}`;
      card.dataset.sourceName = rollup.source_name;

      const top = document.createElement("div");
      top.className = "source-health-heading";

      const name = document.createElement("p");
      name.className = "source-health-name";
      name.textContent = rollup.source_name;

      const badge = document.createElement("span");
      badge.className = `health-badge ${rollup.latest_status}`;
      badge.textContent = `${percentageLabel(rollup.failure_rate)} fail`;

      top.append(name, badge);

      const detail = document.createElement("p");
      detail.className = "source-health-detail";
      detail.textContent = `${rollup.failing_runs} failing of ${rollup.total_runs} runs · latest ${relativeTime(rollup.latest_ran_at)}`;

      const bar = document.createElement("div");
      bar.className = "source-health-rollup-bar";
      const fill = document.createElement("span");
      fill.className = "source-health-rollup-fill";
      fill.style.width = `${(rollup.failure_rate || 0) > 0 ? Math.max(0.08, Math.min(rollup.failure_rate || 0, 1)) * 100 : 0}%`;
      bar.appendChild(fill);

      const sparkline = createSourceHealthSparkline(rollup.recent_statuses || []);

      const actions = document.createElement("div");
      actions.className = "source-health-rollup-actions";

      const filterButton = document.createElement("button");
      filterButton.type = "button";
      filterButton.className = "source-health-action";
      filterButton.dataset.action = "filter-source-runs";
      filterButton.dataset.sourceName = rollup.source_name;
      filterButton.textContent = "Preview runs";

      const historyButton = document.createElement("button");
      historyButton.type = "button";
      historyButton.className = "source-health-action";
      historyButton.dataset.action = "open-source-health-modal";
      historyButton.dataset.sourceName = rollup.source_name;
      historyButton.textContent = "Full history";

      actions.append(filterButton, historyButton);
      card.append(top, detail, bar, sparkline, actions);
      elements.sourceHealthRollups.appendChild(card);
    });
  }

  const runsHead = document.createElement("div");
  runsHead.className = "source-health-runs-head";

  const runsLabel = document.createElement("p");
  runsLabel.className = "profile-meta";
  runsLabel.textContent = state.sourceHealthSelectedSource
    ? `Recent runs for ${state.sourceHealthSelectedSource}`
    : "Recent ingest runs";
  runsHead.appendChild(runsLabel);

  if (state.sourceHealthSelectedSource) {
    const modalButton = document.createElement("button");
    modalButton.type = "button";
    modalButton.className = "source-health-clear-filter";
    modalButton.dataset.action = "open-source-health-modal";
    modalButton.dataset.sourceName = state.sourceHealthSelectedSource;
    modalButton.textContent = "Full history";
    runsHead.appendChild(modalButton);

    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.className = "source-health-clear-filter";
    clearButton.dataset.action = "clear-source-health-filter";
    clearButton.textContent = "Show all";
    runsHead.appendChild(clearButton);
  }

  elements.sourceHealthRuns.appendChild(runsHead);

  if (!(runs || []).length) {
    const emptyRuns = document.createElement("p");
    emptyRuns.className = "profile-empty";
    emptyRuns.textContent = state.sourceHealthSelectedSource
      ? `No stored runs matched ${state.sourceHealthSelectedSource} in the current history window.`
      : "Recent run history will appear after refreshes or CLI ingests.";
    elements.sourceHealthRuns.appendChild(emptyRuns);
    return;
  }

  runs.slice(0, 6).forEach((run) => {
    const row = document.createElement("article");
    row.className = "source-health-run";

    const top = document.createElement("div");
    top.className = "source-health-run-top";

    const name = document.createElement("p");
    name.className = "source-health-run-name";
    name.textContent = run.source_name;

    const badge = document.createElement("span");
    badge.className = `health-badge ${run.status}`;
    badge.textContent = run.status === "error" ? "Error" : "OK";

    top.append(name, badge);

    const meta = document.createElement("p");
    meta.className = "source-health-run-meta";
    meta.textContent = `${relativeTime(run.ran_at)} · fetched ${run.fetched_count} · stored ${run.persisted_count} · failures ${run.consecutive_failures}`;

    row.append(top, meta);

    if (run.last_error) {
      const errorText = document.createElement("p");
      errorText.className = "source-health-context";
      errorText.textContent = run.last_error;
      row.appendChild(errorText);
    }

    if (run.request_id) {
      const requestId = document.createElement("p");
      requestId.className = "source-health-request-id";
      requestId.textContent = `Request ${compactRequestId(run.request_id)}`;
      row.appendChild(requestId);
    }

    elements.sourceHealthRuns.appendChild(row);
  });
}

function renderSourceHealthUnavailable() {
  elements.sourceHealthMeta.textContent = "Source health is unavailable right now.";
  state.sourceHealthRollupItems = [];
  elements.sourceHealthSummary.replaceChildren();
  elements.sourceHealthRollups.replaceChildren();
  elements.sourceHealthRuns.replaceChildren();

  const summaryEmpty = document.createElement("p");
  summaryEmpty.className = "profile-empty";
  summaryEmpty.textContent = "The feed is still usable, but the source monitor could not load.";
  elements.sourceHealthSummary.appendChild(summaryEmpty);
}

async function loadSourceHealthPanel(options = {}) {
  const { silent = true, sourceName = state.sourceHealthSelectedSource || "" } = options;
  state.sourceHealthSelectedSource = sourceName;
  elements.sourceHealthMeta.textContent = "Loading source health...";

  try {
    const runsPath = sourceName
      ? `/api/source-health/runs?limit=8&source_name=${encodeURIComponent(sourceName)}`
      : "/api/source-health/runs?limit=8";
    const [summary, rollups, runPayload] = await Promise.all([
      apiRequest("/api/source-health"),
      apiRequest("/api/source-health/rollups?window_hours=24&limit=6"),
      apiRequest(runsPath),
    ]);
    renderSourceHealth(summary, rollups, runPayload.items || []);
  } catch (error) {
    console.error(error);
    renderSourceHealthUnavailable();
    if (!silent) {
      setStatus("Source monitor refresh failed. The feed is still available.", true);
    }
  }
}

function showSourceHealthModal() {
  if (!elements.sourceHealthModal.open) {
    elements.sourceHealthModal.showModal();
  }
}

function closeSourceHealthModal() {
  if (elements.sourceHealthModal.open) {
    elements.sourceHealthModal.close();
  }
}

function renderSourceHealthModalSkeleton(sourceName) {
  elements.sourceHealthModalTitle.textContent = sourceName;
  elements.sourceHealthModalMeta.textContent = "Loading recent source history...";
  elements.sourceHealthModalStatus.textContent = "Fetching the most recent run details and error history.";
  elements.sourceHealthModalList.replaceChildren();
}

function renderSourceHealthModal(sourceName, runs) {
  const summary = summarizeSourceRuns(runs);
  const activeRollup = (state.sourceHealthRollupItems || []).find((item) => item.source_name === sourceName) || null;

  elements.sourceHealthModalTitle.textContent = sourceName;
  elements.sourceHealthModalMeta.textContent = `${summary.totalRuns} recent runs · ${percentageLabel(summary.failureRate)} failing · latest ${summary.latestRun ? relativeTime(summary.latestRun.ran_at) : "unknown"}`;
  elements.sourceHealthModalStatus.textContent = activeRollup?.latest_error
    ? activeRollup.latest_error
    : summary.latestRun?.last_error || "Review the most recent run outcomes and request IDs below.";
  elements.sourceHealthModalList.replaceChildren();

  if (!runs.length) {
    const empty = document.createElement("p");
    empty.className = "profile-empty";
    empty.textContent = "No stored runs are available for this source yet.";
    elements.sourceHealthModalList.appendChild(empty);
    return;
  }

  runs.forEach((run) => {
    const item = document.createElement("article");
    item.className = `source-health-modal-item ${run.status}`;

    const top = document.createElement("div");
    top.className = "source-health-run-top";

    const name = document.createElement("p");
    name.className = "source-health-run-name";
    name.textContent = `${run.status === "error" ? "Failure" : "Healthy run"} · ${relativeTime(run.ran_at)}`;

    const badge = document.createElement("span");
    badge.className = `health-badge ${run.status}`;
    badge.textContent = run.status === "error" ? "Error" : "OK";

    top.append(name, badge);

    const meta = document.createElement("p");
    meta.className = "source-health-run-meta";
    meta.textContent = `Fetched ${run.fetched_count} · Stored ${run.persisted_count} · Error count ${run.error_count} · Consecutive failures ${run.consecutive_failures}`;

    item.append(top, meta);

    if (run.last_error) {
      const errorText = document.createElement("p");
      errorText.className = "source-health-context";
      errorText.textContent = run.last_error;
      item.appendChild(errorText);
    }

    if (run.request_id) {
      const requestId = document.createElement("p");
      requestId.className = "source-health-request-id";
      requestId.textContent = `Request ${run.request_id}`;
      item.appendChild(requestId);
    }

    elements.sourceHealthModalList.appendChild(item);
  });
}

async function openSourceHealthModal(sourceName, options = {}) {
  const { silent = true } = options;
  state.sourceHealthModalSource = sourceName;
  const requestId = ++state.sourceHealthModalRequestId;
  renderSourceHealthModalSkeleton(sourceName);
  showSourceHealthModal();

  try {
    const payload = await apiRequest(`/api/source-health/runs?limit=30&source_name=${encodeURIComponent(sourceName)}`);
    if (requestId !== state.sourceHealthModalRequestId) {
      return;
    }
    renderSourceHealthModal(sourceName, payload.items || []);
  } catch (error) {
    if (requestId !== state.sourceHealthModalRequestId) {
      return;
    }
    console.error(error);
    elements.sourceHealthModalMeta.textContent = "Unable to load source run history.";
    elements.sourceHealthModalStatus.textContent = "The source monitor is still available, but the full history request failed.";
    elements.sourceHealthModalList.replaceChildren();
    if (!silent) {
      setStatus(`Unable to load full source history for ${sourceName}.`, true);
    }
  }
}

function renderEntityGroups(groups, items) {
  elements.entitySummary.replaceChildren();
  if (!groups.length) {
    const empty = document.createElement("p");
    empty.className = "profile-empty";
    empty.textContent = "As related coverage accumulates, shared events and franchises will cluster here.";
    elements.entitySummary.appendChild(empty);
    return;
  }

  groups.forEach((group) => {
    const relatedItems = items.filter((item) => (item.entity_tags || []).includes(group.name));
    const block = document.createElement("details");
    block.className = "entity-group-card";
    block.open = relatedItems.length <= 2;

    const summary = document.createElement("summary");
    summary.className = "entity-group-summary";

    const summaryTitle = document.createElement("p");
    summaryTitle.className = "entity-name";
    summaryTitle.textContent = group.name;

    const meta = document.createElement("p");
    meta.className = "profile-meta";
    meta.textContent = `${group.kind} · ${group.count} stories · ${group.source_count} sources`;

    summary.append(summaryTitle, meta);

    const body = document.createElement("div");
    body.className = "entity-group-body";

    const headline = document.createElement("p");
    headline.className = "entity-headline";
    headline.textContent = group.headline;

    const controls = document.createElement("div");
    controls.className = "chip-row";
    controls.appendChild(
      createEntityActionGroup(group.name, {
        focusClassName: "entity-focus-button entity-filter-button",
        focusLabel: `Focus ${group.name}`,
        followClassName: "entity-follow-button entity-follow-button-wide",
        includeDetail: true,
        detailClassName: "entity-detail-button entity-detail-button-wide",
        detailLabel: "Details",
      }),
    );

    const relatedList = document.createElement("div");
    relatedList.className = "cluster-list";
    relatedItems.forEach((item) => {
      const link = document.createElement("a");
      link.className = "cluster-link";
      configureArticleLink(link, item);
      link.textContent = item.title;
      relatedList.appendChild(link);
    });

    const sources = document.createElement("div");
    sources.className = "chip-row";
    (group.source_names || []).forEach((sourceName) => {
      const chip = document.createElement("span");
      chip.className = "chip entity-source-chip";
      chip.textContent = sourceName;
      sources.appendChild(chip);
    });

    body.append(headline, controls, relatedList, sources);
    block.append(summary, body);
    elements.entitySummary.appendChild(block);
  });
}

function appendProfileBlock(title, values) {
  if (!values.length) {
    return;
  }

  const block = document.createElement("div");
  block.className = "profile-group";

  const label = document.createElement("p");
  label.className = "profile-meta";
  label.textContent = title;

  const row = document.createElement("div");
  row.className = "chip-row";
  values.forEach((value) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = value;
    row.appendChild(chip);
  });

  block.append(label, row);
  elements.profileSummary.appendChild(block);
}

function appendPinnedEntityBlock(title, values) {
  if (!values.length) {
    return;
  }

  const block = document.createElement("div");
  block.className = "profile-group";

  const label = document.createElement("p");
  label.className = "profile-meta";
  label.textContent = title;

  const row = document.createElement("div");
  row.className = "profile-entity-grid";
  values.forEach((value) => {
    row.appendChild(
      createEntityActionGroup(value, {
        includeDetail: true,
        detailClassName: "entity-detail-button entity-detail-button-compact",
        detailLabel: "Details",
        followClassName: "entity-follow-button entity-follow-button-compact",
      }),
    );
  });

  block.append(label, row);
  elements.profileSummary.appendChild(block);
}

function renderProfileSummary(profile) {
  elements.profileSummary.replaceChildren();
  if (!profile) {
    const empty = document.createElement("p");
    empty.className = "profile-empty";
    empty.textContent = "Pin a few interests or start searching. The feed will learn from searches, opens, and hides.";
    elements.profileSummary.appendChild(empty);
    return;
  }

  const intro = document.createElement("p");
  intro.className = "profile-empty";
  const label = profile.display_name || profile.user_id;
  intro.textContent = `${label} has ${profile.interaction_count} recorded signals. Searches and feedback will keep shifting the ranking.`;
  elements.profileSummary.appendChild(intro);

  appendProfileBlock("Pinned categories", profile.pinned_categories || []);
  appendPinnedEntityBlock("Pinned clusters", profile.pinned_entities || []);
  appendProfileBlock("Pinned regions", profile.pinned_regions || []);
  appendProfileBlock("Learned categories", profile.top_categories || []);
  appendProfileBlock("Learned tags", profile.top_tags || []);
  appendProfileBlock("Learned entities", profile.top_entities || []);
  appendProfileBlock("Recent queries", profile.recent_queries || []);
}

function eventMetadataEntries(metadata) {
  if (!metadata) {
    return [];
  }

  return [
    ["Type", metadata.event_type],
    ["Date", metadata.date_label],
    ["Venue", metadata.venue],
    ["Tickets", metadata.ticket_status],
    ["Guests", metadata.guest_names?.length ? metadata.guest_names.join(", ") : metadata.guest_status],
    ["Merch", metadata.merch_status],
  ].filter(([, value]) => value);
}

function renderEventMetadata(metadata) {
  const entries = eventMetadataEntries(metadata);
  if (!entries.length) {
    return null;
  }

  const list = document.createElement("dl");
  list.className = "event-metadata-grid";
  entries.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "event-metadata-item";

    const term = document.createElement("dt");
    term.textContent = label;

    const detail = document.createElement("dd");
    detail.textContent = value;

    item.append(term, detail);
    list.appendChild(item);
  });
  return list;
}

function renderClusterDetailControls(entityName) {
  elements.clusterDetailControls.replaceChildren();
  elements.clusterDetailControls.appendChild(
    createEntityActionGroup(entityName, {
      focusClassName: "entity-focus-button entity-filter-button",
      focusLabel: `Focus ${entityName}`,
      followClassName: "entity-follow-button entity-follow-button-wide",
      includeDetail: false,
    }),
  );
}

function renderClusterDetail(entityName, items, group, statusText = "") {
  state.clusterDetailEntity = entityName;
  const resolvedGroup = buildEntityGroupSnapshot(entityName, items, group);
  const resolvedItems = items || [];

  elements.clusterDetailTitle.textContent = entityName;
  elements.clusterDetailMeta.textContent = `${resolvedGroup.kind} · ${resolvedGroup.count} stories · ${resolvedGroup.source_count} sources`;
  elements.clusterDetailStatus.textContent = statusText;
  renderClusterDetailControls(entityName);

  elements.clusterDetailSources.replaceChildren();
  (resolvedGroup.source_names || []).forEach((sourceName) => {
    const chip = document.createElement("span");
    chip.className = "chip entity-source-chip";
    chip.textContent = sourceName;
    elements.clusterDetailSources.appendChild(chip);
  });

  elements.clusterDetailList.replaceChildren();
  if (!resolvedItems.length) {
    const empty = document.createElement("p");
    empty.className = "profile-empty";
    empty.textContent = "No stored stories are currently grouped under this cluster.";
    elements.clusterDetailList.appendChild(empty);
    return;
  }

  resolvedItems.forEach((item) => {
    const article = document.createElement("article");
    article.className = "cluster-detail-item";

    const topline = document.createElement("div");
    topline.className = "card-topline";

    const source = document.createElement("span");
    source.className = "source-pill";
    source.textContent = item.source_name;

    const resultType = document.createElement("span");
    resultType.className = "result-type-pill";
    decorateResultTypePill(resultType, item);

    const time = document.createElement("span");
    time.className = "time-pill";
    time.textContent = new Date(item.published_at).getTime() > Date.now() ? `Starts ${relativeTime(item.published_at)}` : relativeTime(item.published_at);

    topline.append(source, resultType, time);

    const title = document.createElement("h3");
    title.className = "card-title";
    title.textContent = item.title;

    const summary = document.createElement("p");
    summary.className = "card-summary";
    summary.textContent = item.summary || item.content || "No summary available.";

    const metadata = renderEventMetadata(item.event_metadata);

    const entities = document.createElement("div");
    entities.className = "chip-row entities";
    renderEntityButtons(entities, item.entity_tags || []);

    const footer = document.createElement("div");
    footer.className = "card-footer";

    const scoreMeter = document.createElement("div");
    scoreMeter.className = "score-meter";
    const scoreLabel = document.createElement("span");
    scoreLabel.className = "score-label";
    scoreLabel.textContent = "SG Relevance";
    const scoreBar = document.createElement("div");
    scoreBar.className = "score-bar";
    const scoreFill = document.createElement("span");
    scoreFill.className = "score-fill";
    scoreFill.style.width = `${Math.max(0.12, Math.min(item.sg_relevance || 0, 1)) * 100}%`;
    scoreBar.appendChild(scoreFill);
    scoreMeter.append(scoreLabel, scoreBar);

    const readLink = document.createElement("a");
    readLink.className = "read-link cluster-detail-link";
    configureArticleLink(readLink, item, articleLinkLabel(item));

    footer.append(scoreMeter, readLink);
    article.append(topline, title, summary);
    if (metadata) {
      article.appendChild(metadata);
    }
    article.append(entities, footer);
    elements.clusterDetailList.appendChild(article);
  });
}

function showClusterDetailModal() {
  if (!elements.clusterDetailModal.open) {
    elements.clusterDetailModal.showModal();
  }
}

function closeClusterDetailModal(options = {}) {
  const { updateRoute = true, routeMode = "push" } = options;
  if (elements.clusterDetailModal.open) {
    state.suppressModalRouteSync = !updateRoute;
    state.pendingModalRouteMode = routeMode;
    elements.clusterDetailModal.close();
    return;
  }

  if (updateRoute) {
    writeRouteState({ entity: "" }, { mode: routeMode });
  }
}

async function openClusterDetail(entityName, options = {}) {
  const { updateRoute = true, routeMode = "push" } = options;
  const fallbackItems = currentEntityItems(entityName);
  const fallbackGroup = buildEntityGroupSnapshot(entityName, fallbackItems, currentEntityGroup(entityName));
  const requestId = ++state.clusterDetailRequestId;

  renderClusterDetail(
    entityName,
    fallbackItems,
    fallbackGroup,
    fallbackItems.length ? "Loading broader coverage from the current store..." : "Loading cluster coverage...",
  );
  showClusterDetailModal();
  if (updateRoute) {
    writeRouteState({ entity: entityName }, { mode: routeMode });
  }

  try {
    const payload = await apiRequest("/api/search", {
      method: "POST",
      body: JSON.stringify({ query: entityName, limit: 18, rerank: true, include_digest: false }),
    });
    if (requestId !== state.clusterDetailRequestId) {
      return;
    }

    const filteredItems = (payload.items || []).filter((item) => (item.entity_tags || []).includes(entityName));
    const resolvedItems = filteredItems.length ? filteredItems : fallbackItems;
    const resolvedGroup = buildEntityGroupSnapshot(
      entityName,
      resolvedItems,
      (payload.entity_groups || []).find((group) => group.name === entityName) || fallbackGroup,
    );
    renderClusterDetail(
      entityName,
      resolvedItems,
      resolvedGroup,
      filteredItems.length
        ? "Expanded cluster view from the current store."
        : resolvedItems.length
          ? "Showing the closest stored coverage for this cluster."
          : "No stored stories are currently grouped under this cluster.",
    );
  } catch (error) {
    if (requestId !== state.clusterDetailRequestId) {
      return;
    }
    console.error(error);
    renderClusterDetail(
      entityName,
      fallbackItems,
      fallbackGroup,
      fallbackItems.length
        ? "Showing the current-feed snapshot only. Live detail lookup failed."
        : "Unable to load a broader cluster snapshot right now.",
    );
    setStatus("Unable to load the full cluster detail view.", true);
  }
}

function renderClusterCard(entry) {
  const { leadItem, items, entityName, group } = entry;
  const details = document.createElement("details");
  details.className = "news-card cluster-card reveal-card";

  const summary = document.createElement("summary");
  summary.className = "cluster-card-summary";

  const topline = document.createElement("div");
  topline.className = "card-topline";

  const source = document.createElement("span");
  source.className = "source-pill";
  source.textContent = `${group?.source_count || new Set(items.map((item) => item.source_name)).size} sources`;

  const time = document.createElement("span");
  time.className = "time-pill";
  time.textContent = `${items.length} related stories`;

  topline.append(source, time);

  const title = document.createElement("h3");
  title.className = "card-title";
  title.textContent = entityName;

  const summaryText = document.createElement("p");
  summaryText.className = "card-summary";
  summaryText.textContent = group?.headline || leadItem.title;

  const entities = document.createElement("div");
  entities.className = "chip-row entities";
  entities.appendChild(createEntityButton(entityName));

  summary.append(topline, title, summaryText, entities);

  const body = document.createElement("div");
  body.className = "cluster-card-body";

  const leadSummary = document.createElement("p");
  leadSummary.className = "cluster-lead-summary";
  leadSummary.textContent = leadItem.summary || leadItem.content || "No summary available.";

  const links = document.createElement("div");
  links.className = "cluster-list";
  items.forEach((item) => {
    const link = document.createElement("a");
    link.className = "cluster-link";
    configureArticleLink(link, item);
    link.textContent = `${item.title} · ${item.source_name}`;
    links.appendChild(link);
  });

  const actions = document.createElement("div");
  actions.className = "card-actions";

  const likeButton = document.createElement("button");
  likeButton.type = "button";
  likeButton.className = "signal-button";
  likeButton.dataset.action = "like";
  likeButton.dataset.articleId = leadItem.id;
  likeButton.textContent = `Boost ${entityName}`;

  const dismissButton = document.createElement("button");
  dismissButton.type = "button";
  dismissButton.className = "signal-button";
  dismissButton.dataset.action = "dismiss";
  dismissButton.dataset.articleId = leadItem.id;
  dismissButton.textContent = `Hide ${entityName}`;

  const followButton = createEntityFollowButton(entityName, "entity-follow-button entity-follow-button-wide");
  const detailButton = createEntityDetailButton(entityName, "entity-detail-button entity-detail-button-wide", "Cluster detail");

  actions.append(detailButton, followButton, likeButton, dismissButton);

  const footer = document.createElement("div");
  footer.className = "card-footer";

  const scoreMeter = document.createElement("div");
  scoreMeter.className = "score-meter";
  const scoreLabel = document.createElement("span");
  scoreLabel.className = "score-label";
  scoreLabel.textContent = "Lead SG Relevance";
  const scoreBar = document.createElement("div");
  scoreBar.className = "score-bar";
  const scoreFill = document.createElement("span");
  scoreFill.className = "score-fill";
  scoreFill.style.width = `${Math.max(0.12, Math.min(leadItem.sg_relevance || 0, 1)) * 100}%`;
  scoreBar.appendChild(scoreFill);
  scoreMeter.append(scoreLabel, scoreBar);

  const readLink = document.createElement("a");
  readLink.className = "read-link";
  configureArticleLink(readLink, leadItem, articleLinkLabel(leadItem));

  footer.append(scoreMeter, readLink);
  body.append(leadSummary, links, actions, footer);
  details.append(summary, body);
  return details;
}

function renderCards(items, groups = []) {
  elements.cardsContainer.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = "No stories matched the current view.";
    elements.cardsContainer.appendChild(empty);
    return;
  }

  groupFeedEntries(items, groups).forEach((entry) => {
    if (entry.type === "cluster") {
      elements.cardsContainer.appendChild(renderClusterCard(entry));
      return;
    }

    const { item } = entry;
    const fragment = elements.articleTemplate.content.cloneNode(true);
    const card = fragment.querySelector(".news-card");
    const timeLabel = fragment.querySelector(".time-pill");
    const link = fragment.querySelector(".read-link");

    card.dataset.articleId = item.id;
    fragment.querySelector(".source-pill").textContent = item.source_name;
    decorateResultTypePill(fragment.querySelector(".result-type-pill"), item);
    timeLabel.textContent = new Date(item.published_at).getTime() > Date.now() ? `Starts ${relativeTime(item.published_at)}` : relativeTime(item.published_at);
    fragment.querySelector(".card-title").textContent = item.title;
    fragment.querySelector(".card-summary").textContent = item.summary || item.content || "No summary available.";

    renderEntityButtons(fragment.querySelector(".entities"), item.entity_tags || []);
    renderChips(fragment.querySelector(".tags"), item.tags || []);
    renderChips(fragment.querySelector(".regions"), item.region_tags || []);

    const scoreFill = fragment.querySelector(".score-fill");
    scoreFill.style.width = `${Math.max(0.12, Math.min(item.sg_relevance || 0, 1)) * 100}%`;

    configureArticleLink(link, item, articleLinkLabel(item));

    fragment.querySelectorAll(".signal-button").forEach((button) => {
      button.dataset.articleId = item.id;
    });

    elements.cardsContainer.appendChild(fragment);
  });
}

function renderFeed(payload, mode) {
  const itemCount = payload.items.length;
  const generatedAt = new Date(payload.generated_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  state.currentItems = payload.items || [];
  state.currentGroups = payload.entity_groups || [];

  if (payload.profile) {
    applyProfileState(payload.profile);
  }

  renderDigest(payload.digest || [], mode === "search" ? "Why these headlines" : "Top signals right now");
  renderSourceBreakdown(payload.source_breakdown || {});
  renderEntityGroups(payload.entity_groups || [], payload.items || []);
  renderCards(payload.items || [], payload.entity_groups || []);

  if (mode === "search") {
    elements.feedTitle.textContent = `Prompt-ranked results for “${payload.query}”`;
    elements.feedMeta.textContent = `Expanded to: ${payload.expanded_query || payload.query} · ${itemCount} stories · ${generatedAt}`;
  } else {
    elements.feedTitle.textContent = "Singapore-weighted headline stack";
    elements.feedMeta.textContent = `${itemCount} stories · refreshed ${generatedAt}`;
  }
}

async function syncProfile(options = {}) {
  const { silent = false } = options;
  if (!silent) {
    setStatus("Saving profile preferences...");
  }

  const profile = await apiRequest("/api/profile", {
    method: "POST",
    body: JSON.stringify(buildProfilePayload()),
  });
  applyProfileState(profile);
  writeStoredProfile();

  if (!silent) {
    setStatus("Profile preferences saved.");
  }
  return profile;
}

async function loadHomeFeed(options = {}) {
  const { updateRoute = true, routeMode = "replace", announce = true } = options;
  cancelPendingSearchDigest();
  state.currentMode = "home";
  state.currentQuery = "";
  elements.queryInput.value = "";
  if (announce) {
    setStatus("Loading the personalized home feed...");
  }
  const payload = await apiRequest(`/api/news?limit=12&user_id=${encodeURIComponent(state.userId)}`);
  renderFeed(payload, "home");
  if (updateRoute) {
    writeRouteState({ query: "" }, { mode: routeMode });
  }
  if (announce) {
    setStatus("Showing the latest Singapore-weighted headlines for this profile.");
  }
}

async function runSearch(query, options = {}) {
  const { updateRoute = true, routeMode = "replace", trackProfile = true } = options;
  cancelPendingSearchDigest();
  state.currentMode = "search";
  state.currentQuery = query;
  elements.queryInput.value = query;
  setStatus(`Searching for ${query}...`);
  const payload = await apiRequest("/api/search", {
    method: "POST",
    body: JSON.stringify({ query, limit: 12, rerank: true, user_id: state.userId, track_profile: trackProfile, include_digest: false }),
  });
  renderFeed(payload, "search");
  void loadDeferredSearchDigest(query, payload.items || []);
  if (updateRoute) {
    writeRouteState({ query }, { mode: routeMode });
  }
  if ((payload.items || []).length === 0) {
    setStatus("No strong matches were found for that query. Try broader SG or SEA terms, or refresh sources.");
  } else {
    setStatus("Search feed updated.");
  }
}

async function restoreCurrentView() {
  if (state.currentMode === "search" && state.currentQuery) {
    await runSearch(state.currentQuery, { updateRoute: false, trackProfile: false });
    return;
  }
  await loadHomeFeed({ updateRoute: false });
}

async function focusEntity(entityName, options = {}) {
  elements.queryInput.value = entityName;
  await runSearch(entityName, options);
  setStatus(`Showing clustered coverage for ${entityName}.`);
}

async function togglePinnedEntity(entityName) {
  const previousPinnedEntities = [...state.pinnedEntities];
  const nextPinnedEntities = isPinnedEntity(entityName)
    ? previousPinnedEntities.filter((value) => value !== entityName)
    : uniqueValues([...previousPinnedEntities, entityName]);

  state.pinnedEntities = nextPinnedEntities;
  syncPinnedEntityCheckboxes();

  try {
    await syncProfile({ silent: true });
    await restoreCurrentView();
    setStatus(
      previousPinnedEntities.includes(entityName)
        ? `Stopped prioritizing ${entityName}.`
        : `Following ${entityName}. Related coverage will surface sooner.`,
    );
  } catch (error) {
    state.pinnedEntities = previousPinnedEntities;
    syncPinnedEntityCheckboxes();
    throw error;
  }
}

function noteOpen(articleId) {
  return apiRequest("/api/interactions", {
    method: "POST",
    body: JSON.stringify({ user_id: state.userId, article_id: articleId, action: "open" }),
  })
    .then((profile) => {
      applyProfileState(profile);
    })
    .catch((error) => {
      console.error(error);
    });
}

async function recordInteraction(articleId, action, refreshView = false) {
  const profile = await apiRequest("/api/interactions", {
    method: "POST",
    body: JSON.stringify({ user_id: state.userId, article_id: articleId, action }),
  });
  applyProfileState(profile);

  if (refreshView) {
    await restoreCurrentView();
  }

  if (action === "like") {
    setStatus("Preference updated. Similar stories will surface sooner.");
  } else if (action === "dismiss") {
    setStatus("That signal was hidden and downweighted for this profile.");
  }
}

async function refreshSources() {
  setStatus("Refreshing sources and updating the article store...");
  const payload = await apiRequest("/api/refresh", { method: "POST" });
  const message = payload.seed_used
    ? "No live sources responded, so demo seed headlines were loaded instead."
    : `Ingestion completed with ${payload.persisted} stored headlines.`;
  if (payload.errors?.length) {
    console.warn("Refresh warnings:", payload.errors);
  }
  const refreshTasks = [loadHomeFeed({ announce: false }), loadSourceHealthPanel({ silent: true })];
  if (elements.sourceHealthModal.open && state.sourceHealthModalSource) {
    refreshTasks.push(openSourceHealthModal(state.sourceHealthModalSource, { silent: true }));
  }
  await Promise.all(refreshTasks);
  setStatus(message, payload.errors?.length > 0);
}

async function applyInitialRoute() {
  const route = readRouteState();
  if (route.query) {
    await runSearch(route.query, { updateRoute: false, trackProfile: false });
  } else {
    await loadHomeFeed({ updateRoute: false });
  }

  if (route.entity) {
    await openClusterDetail(route.entity, { updateRoute: false });
  } else if (elements.clusterDetailModal?.open) {
    closeClusterDetailModal({ updateRoute: false });
  }
}

elements.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = elements.queryInput.value.trim();
  if (!query) {
    await loadHomeFeed({ routeMode: "push" });
    return;
  }

  try {
    await runSearch(query, { routeMode: "push" });
  } catch (error) {
    console.error(error);
    setStatus("Search failed. Check that the API server is running.", true);
  }
});

elements.profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await syncProfile();
    await restoreCurrentView();
  } catch (error) {
    console.error(error);
    setStatus("Unable to save profile preferences.", true);
  }
});

elements.cardsContainer.addEventListener("click", async (event) => {
  const followButton = event.target.closest(".entity-follow-button");
  if (followButton) {
    event.preventDefault();
    try {
      await togglePinnedEntity(followButton.dataset.entityName);
    } catch (error) {
      console.error(error);
      setStatus("Unable to update that followed cluster.", true);
    }
    return;
  }

  const detailButton = event.target.closest(".entity-detail-button");
  if (detailButton) {
    event.preventDefault();
    try {
      await openClusterDetail(detailButton.dataset.entityName);
    } catch (error) {
      console.error(error);
      setStatus("Unable to open that cluster detail view.", true);
    }
    return;
  }

  const entityButton = event.target.closest(".entity-filter-button");
  if (entityButton) {
    event.preventDefault();
    try {
      await focusEntity(entityButton.dataset.entityName, { routeMode: "push" });
    } catch (error) {
      console.error(error);
      setStatus("Unable to pivot to that entity cluster.", true);
    }
    return;
  }

  const actionButton = event.target.closest(".signal-button");
  if (actionButton) {
    event.preventDefault();
    try {
      await recordInteraction(actionButton.dataset.articleId, actionButton.dataset.action, actionButton.dataset.action === "dismiss");
    } catch (error) {
      console.error(error);
      setStatus("Unable to store that feedback signal.", true);
    }
    return;
  }

  const link = event.target.closest(".read-link");
  const clusterLink = event.target.closest(".cluster-link");
  const openTarget = link || clusterLink;
  if (!openTarget) {
    return;
  }

  if (openTarget.dataset.linkDisabled === "true") {
    event.preventDefault();
    setStatus("Original source link is unavailable for this item.", true);
    return;
  }

  noteOpen(openTarget.dataset.articleId);
});

elements.entitySummary.addEventListener("click", async (event) => {
  const followButton = event.target.closest(".entity-follow-button");
  if (followButton) {
    event.preventDefault();
    try {
      await togglePinnedEntity(followButton.dataset.entityName);
    } catch (error) {
      console.error(error);
      setStatus("Unable to update that followed cluster.", true);
    }
    return;
  }

  const detailButton = event.target.closest(".entity-detail-button");
  if (detailButton) {
    event.preventDefault();
    try {
      await openClusterDetail(detailButton.dataset.entityName, { routeMode: "push" });
    } catch (error) {
      console.error(error);
      setStatus("Unable to open that cluster detail view.", true);
    }
    return;
  }

  const entityButton = event.target.closest(".entity-filter-button");
  if (entityButton) {
    event.preventDefault();
    try {
      await focusEntity(entityButton.dataset.entityName, { routeMode: "push" });
    } catch (error) {
      console.error(error);
      setStatus("Unable to pivot to that entity cluster.", true);
    }
    return;
  }

  const clusterLink = event.target.closest(".cluster-link");
  if (!clusterLink) {
    return;
  }

  if (clusterLink.dataset.linkDisabled === "true") {
    event.preventDefault();
    setStatus("Original source link is unavailable for this item.", true);
    return;
  }

  noteOpen(clusterLink.dataset.articleId);
});

elements.profileSummary.addEventListener("click", async (event) => {
  const followButton = event.target.closest(".entity-follow-button");
  if (followButton) {
    event.preventDefault();
    try {
      await togglePinnedEntity(followButton.dataset.entityName);
    } catch (error) {
      console.error(error);
      setStatus("Unable to update that followed cluster.", true);
    }
    return;
  }

  const detailButton = event.target.closest(".entity-detail-button");
  if (detailButton) {
    event.preventDefault();
    try {
      await openClusterDetail(detailButton.dataset.entityName, { routeMode: "push" });
    } catch (error) {
      console.error(error);
      setStatus("Unable to open that cluster detail view.", true);
    }
    return;
  }

  const entityButton = event.target.closest(".entity-filter-button");
  if (!entityButton) {
    return;
  }

  event.preventDefault();
  try {
    await focusEntity(entityButton.dataset.entityName, { routeMode: "push" });
  } catch (error) {
    console.error(error);
    setStatus("Unable to pivot to that entity cluster.", true);
  }
});

elements.sourceHealthRollups.addEventListener("click", async (event) => {
  const historyButton = event.target.closest('[data-action="open-source-health-modal"]');
  if (historyButton) {
    event.preventDefault();
    try {
      await openSourceHealthModal(historyButton.dataset.sourceName, { silent: true });
      setStatus(`Opened full source history for ${historyButton.dataset.sourceName}.`);
    } catch (error) {
      console.error(error);
      setStatus("Unable to open full source history.", true);
    }
    return;
  }

  const rollupButton = event.target.closest('[data-action="filter-source-runs"]');
  if (!rollupButton) {
    return;
  }

  event.preventDefault();
  try {
    await loadSourceHealthPanel({ sourceName: rollupButton.dataset.sourceName, silent: true });
    setStatus(`Showing recent source runs for ${rollupButton.dataset.sourceName}.`);
  } catch (error) {
    console.error(error);
    setStatus("Unable to filter source run history.", true);
  }
});

elements.sourceHealthRuns.addEventListener("click", async (event) => {
  const modalButton = event.target.closest('[data-action="open-source-health-modal"]');
  if (modalButton) {
    event.preventDefault();
    try {
      await openSourceHealthModal(modalButton.dataset.sourceName, { silent: true });
      setStatus(`Opened full source history for ${modalButton.dataset.sourceName}.`);
    } catch (error) {
      console.error(error);
      setStatus("Unable to open full source history.", true);
    }
    return;
  }

  const clearButton = event.target.closest('[data-action="clear-source-health-filter"]');
  if (!clearButton) {
    return;
  }

  event.preventDefault();
  try {
    await loadSourceHealthPanel({ sourceName: "", silent: true });
    setStatus("Showing recent runs across all sources.");
  } catch (error) {
    console.error(error);
    setStatus("Unable to clear the source run filter.", true);
  }
});

elements.sourceHealthModalClose.addEventListener("click", () => {
  closeSourceHealthModal();
});

elements.sourceHealthModal.addEventListener("close", () => {
  state.sourceHealthModalRequestId += 1;
  state.sourceHealthModalSource = "";
});

elements.sourceHealthModal.addEventListener("click", (event) => {
  if (event.target === elements.sourceHealthModal) {
    closeSourceHealthModal();
  }
});

elements.clusterDetailClose.addEventListener("click", () => {
  closeClusterDetailModal({ routeMode: "push" });
});

elements.clusterDetailModal.addEventListener("close", () => {
  const suppressModalRouteSync = state.suppressModalRouteSync;
  const pendingModalRouteMode = state.pendingModalRouteMode;
  state.suppressModalRouteSync = false;
  state.pendingModalRouteMode = "push";
  state.clusterDetailEntity = "";
  state.clusterDetailRequestId += 1;
  if (!suppressModalRouteSync) {
    writeRouteState({ entity: "" }, { mode: pendingModalRouteMode || "push" });
  }
});

elements.clusterDetailModal.addEventListener("click", async (event) => {
  if (event.target === elements.clusterDetailModal) {
    closeClusterDetailModal({ routeMode: "push" });
    return;
  }

  const followButton = event.target.closest(".entity-follow-button");
  if (followButton) {
    event.preventDefault();
    try {
      await togglePinnedEntity(followButton.dataset.entityName);
    } catch (error) {
      console.error(error);
      setStatus("Unable to update that followed cluster.", true);
    }
    return;
  }

  const entityButton = event.target.closest(".entity-filter-button");
  if (entityButton) {
    event.preventDefault();
    closeClusterDetailModal({ routeMode: "push" });
    try {
      await focusEntity(entityButton.dataset.entityName, { routeMode: "push" });
    } catch (error) {
      console.error(error);
      setStatus("Unable to pivot to that entity cluster.", true);
    }
    return;
  }

  const detailLink = event.target.closest(".cluster-detail-link");
  if (!detailLink) {
    return;
  }

  if (detailLink.dataset.linkDisabled === "true") {
    event.preventDefault();
    setStatus("Original source link is unavailable for this item.", true);
    return;
  }

  noteOpen(detailLink.dataset.articleId);
});

window.addEventListener("popstate", () => {
  applyInitialRoute().catch((error) => {
    console.error(error);
    setStatus("Unable to restore the requested feed view from browser history.", true);
  });
});

elements.homeButton.addEventListener("click", async () => {
  elements.queryInput.value = "";
  try {
    await loadHomeFeed();
  } catch (error) {
    console.error(error);
    setStatus("Unable to load the home feed.", true);
  }
});

elements.refreshButton.addEventListener("click", async () => {
  try {
    await refreshSources();
  } catch (error) {
    console.error(error);
    setStatus("Refresh failed. Check source connectivity or API logs.", true);
  }
});

async function initializeApp() {
  hydrateProfileForm();
  renderProfileSummary(null);
  await Promise.all([syncProfile({ silent: true }), loadSourceHealthPanel()]);
  await applyInitialRoute();
}

initializeApp().catch((error) => {
  console.error(error);
  setStatus("Unable to connect to the API. Start the FastAPI server and try again.", true);
});
