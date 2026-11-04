"use strict";

const ProductUI = (() => {
  const $ = selector => document.querySelector(selector);
  const fields = Object.fromEntries(["name", "model", "category", "price", "description"].map(key => [key, $(`#product-${key}`)]));
  const data = { route: "", id: null, revision: null, loaded: false, saving: false, baseline: "", epoch: 0, query: "", offset: 0, total: 0, limit: 20, touched: new Set(), flash: "" };
  let searchTimer;
  const values = () => Object.fromEntries(Object.entries(fields).map(([key, element]) => [key, element.value]));
  const dirty = () => data.loaded && JSON.stringify(values()) !== data.baseline;
  const count = value => Array.from(value).length;

  function message(text = "", error = false) {
    $("#product-message").textContent = text;
    $("#product-message").className = `message${error ? " error" : ""}`;
    $("#product-message").hidden = !text;
  }

  function errors() {
    const value = values();
    const found = {};
    for (const [key, maximum, label] of [["name", 120, "商品名称"], ["model", 64, "商品型号"], ["category", 80, "分类"]]) {
      const text = value[key].trim();
      if ((key !== "category" && !text) || count(text) > maximum) found[key] = `${label}需要${key === "category" ? "不超过" : "填写 1 到"} ${maximum} 个字符。`;
      if (/\p{C}/u.test(text)) found[key] = `${label}中不能包含控制字符。`;
    }
    if (count(value.model.trim().normalize("NFKC")) > 64) found.model = "商品型号需要填写 1 到 64 个字符。";
    if (count(value.description.trim()) > 4000) found.description = "商品说明不能超过 4000 个字符。";
    if (Array.from(value.description).some(char => /\p{C}/u.test(char) && char !== "\n" && char !== "\t")) found.description = "商品说明中包含无法保存的控制字符。";
    const price = value.price.trim();
    if (price && (!/^\d+(?:\.\d{1,2})?$/.test(price) || Number(price) > 9999999.99)) found.price = "请填写 0 到 9999999.99 之间的金额，最多保留两位小数。";
    return found;
  }

  function validate(all = false) {
    const found = errors();
    for (const key of Object.keys(fields)) {
      const text = (all || data.touched.has(key)) ? found[key] || "" : "";
      fields[key].setAttribute("aria-invalid", String(Boolean(text)));
      $(`#product-${key}-error`).textContent = text;
      $(`#product-${key}-error`).hidden = !text;
    }
    $("#save-product").disabled = data.saving || !data.loaded || (data.id !== null && !dirty());
    $("#product-save-state").textContent = data.saving ? "正在保存" : !data.loaded ? "" : dirty() ? "有未保存的修改" : data.id ? "与已保存内容一致" : "填写后保存";
    return found;
  }

  function fill(product) {
    data.id = product?.id ?? null;
    data.revision = product?.revision ?? null;
    for (const key of ["name", "model", "category", "description"]) fields[key].value = product?.[key] || "";
    fields.price.value = product?.price_cents == null ? "" : (product.price_cents / 100).toFixed(2);
    data.baseline = JSON.stringify(values());
    data.touched.clear();
    data.loaded = true;
    $("#product-fields").disabled = false;
    $("#products-title").textContent = product ? "编辑商品" : "新建商品";
    $("#products-subtitle").textContent = product ? "修改后保存，商品列表会显示最新资料。" : "先保存基本资料，之后可以随时继续修改。";
    $("#save-product").textContent = product ? "保存修改" : "保存商品";
    $("#reload-product").hidden = true;
    validate();
  }

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function renderList(result) {
    const list = $("#product-list");
    list.replaceChildren();
    for (const product of result.items) {
      const row = element("li", undefined, "product-row");
      const identity = element("div", undefined, "product-identity");
      const link = element("a", product.name, "product-name-link");
      link.href = `#/products/${product.id}`;
      identity.append(link, element("span", product.category || "未分类", "product-category-label"));
      const model = element("div", product.model, "product-model-value");
      const price = element("div", product.price_cents == null ? "未设置" : `¥ ${(product.price_cents / 100).toFixed(2)}`, "product-price-value");
      const updated = element("time", formatDate(product.updated_at), "product-time-value");
      updated.dateTime = product.updated_at;
      const edit = element("a", "编辑", "product-edit-link");
      edit.href = link.href;
      edit.setAttribute("aria-label", `编辑 ${product.name}`);
      row.append(identity, model, price, updated, edit);
      list.append(row);
    }
    $("#product-result-count").textContent = data.query ? `找到 ${result.total} 件商品` : `共 ${result.total} 件商品`;
    $("#products-empty").hidden = result.total !== 0;
    $("#products-empty-title").textContent = data.query ? "没有找到匹配的商品" : "还没有商品";
    $("#products-empty-description").textContent = data.query ? "换个名称或型号试试，也可以清空搜索条件。" : "先添加第一件商品，把基本资料保存下来。";
    $("#empty-new-product").hidden = Boolean(data.query);
    $("#product-results").hidden = result.items.length === 0;
    $("#product-pagination").hidden = result.total <= data.limit;
    $("#product-page-info").textContent = `第 ${Math.floor(data.offset / data.limit) + 1} / ${Math.max(1, Math.ceil(result.total / data.limit))} 页`;
    $("#products-prev").disabled = data.offset === 0;
    $("#products-next").disabled = data.offset + data.limit >= result.total;
  }

  async function loadList() {
    const epoch = ++data.epoch;
    $("#product-list-error").hidden = true;
    $("#products-loading").hidden = false;
    $("#products-empty").hidden = true;
    $("#product-results").hidden = true;
    $("#product-pagination").hidden = true;
    $("#product-result-count").textContent = "";
    $("#clear-product-search").hidden = !data.query;
    $("#retry-products").disabled = true;
    try {
      const parameters = new URLSearchParams({ q: data.query, limit: data.limit, offset: data.offset });
      const result = await request(`/api/products?${parameters}`);
      if (epoch !== data.epoch) return;
      data.total = result.total;
      if (data.offset && data.offset >= result.total) {
        data.offset = Math.max(0, Math.ceil(result.total / data.limit) - 1) * data.limit;
        return loadList();
      }
      renderList(result);
      connection(true);
    } catch {
      if (epoch !== data.epoch) return;
      $("#product-list-error").hidden = false;
      connection(false);
    } finally {
      if (epoch === data.epoch) {
        $("#products-loading").hidden = true;
        $("#retry-products").disabled = false;
      }
    }
  }

  async function loadProduct(id) {
    const epoch = ++data.epoch;
    data.loaded = false;
    $("#product-fields").disabled = true;
    $("#product-loading").hidden = false;
    $("#product-load-error").hidden = true;
    $("#retry-product").disabled = true;
    message();
    validate();
    try {
      const product = await request(`/api/products/${id}`);
      if (epoch !== data.epoch) return;
      fill(product);
      message(data.flash);
      data.flash = "";
      connection(true);
    } catch (error) {
      if (epoch !== data.epoch) return;
      $("#product-load-error").hidden = false;
      $("#product-load-error-text").textContent = error.status === 404 ? "没有找到这件商品，可以返回列表重新选择。" : "暂时无法读取商品，稍后可以重试。";
      $("#retry-product").hidden = error.status === 404;
      if (error.status !== 404) connection(false);
    } finally {
      if (epoch === data.epoch) {
        $("#product-loading").hidden = true;
        $("#retry-product").disabled = false;
      }
    }
  }

  function enter(hash) {
    if (hash === data.route) return;
    data.route = hash;
    data.epoch++;
    data.loaded = false;
    const list = hash === "#/products";
    $("#product-list-panel").hidden = !list;
    $("#product-editor").hidden = list;
    $("#new-product").hidden = !list;
    if (list) {
      $("#products-title").textContent = "商品管理";
      $("#products-subtitle").textContent = "查找商品，维护名称和型号，以及售价等基本资料。";
      $("#product-search").value = data.query;
      loadList();
    } else {
      $("#product-form").reset();
      $("#product-load-error").hidden = true;
      $("#product-loading").hidden = true;
      $("#retry-product").hidden = false;
      $("#reload-product").hidden = true;
      message();
      if (hash.endsWith("/new")) {
        fill(null);
        fields.name.focus();
      } else {
        $("#products-title").textContent = "编辑商品";
        $("#products-subtitle").textContent = "修改后保存，商品列表会显示最新资料。";
        loadProduct(hash.split("/").pop());
      }
    }
  }

  function canLeave(hash) {
    if (hash === data.route) return true;
    if (data.saving) { message("正在保存，请稍等。"); return false; }
    return !dirty() || window.confirm("还有未保存的商品内容，确定离开吗？");
  }

  function hide() {
    clearTimeout(searchTimer);
    data.epoch++;
    data.route = "";
    data.loaded = false;
  }

  function search() {
    clearTimeout(searchTimer);
    if (data.route !== "#/products") return;
    data.query = $("#product-search").value.trim();
    data.offset = 0;
    loadList();
  }

  $("#product-search-form").addEventListener("submit", event => { event.preventDefault(); search(); });
  $("#product-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(search, 250); });
  $("#clear-product-search").addEventListener("click", () => { $("#product-search").value = ""; search(); $("#product-search").focus(); });
  $("#retry-products").addEventListener("click", loadList);
  $("#products-prev").addEventListener("click", () => { data.offset = Math.max(0, data.offset - data.limit); loadList(); });
  $("#products-next").addEventListener("click", () => { data.offset += data.limit; loadList(); });
  $("#retry-product").addEventListener("click", () => loadProduct(data.route.split("/").pop()));
  $("#reload-product").addEventListener("click", () => {
    if (!dirty() || window.confirm("载入最新资料会替换当前未保存的内容，确定继续吗？")) loadProduct(data.id);
  });
  for (const [key, input] of Object.entries(fields)) {
    input.addEventListener("input", () => { data.touched.add(key); message(); validate(); });
  }
  window.addEventListener("beforeunload", event => {
    if (dirty() || data.saving) { event.preventDefault(); event.returnValue = ""; }
  });

  $("#product-form").addEventListener("submit", async event => {
    event.preventDefault();
    if (!data.loaded || data.saving) return;
    const found = validate(true);
    if (Object.keys(found).length) { fields[Object.keys(found)[0]].focus(); return; }
    if (data.id && !dirty()) return;
    const value = values();
    const price = value.price.trim();
    const [whole, fraction = ""] = price.split(".");
    const payload = { name: value.name, model: value.model, category: value.category, description: value.description, price_cents: price ? Number(whole) * 100 + Number(fraction.padEnd(2, "0")) : null };
    const creating = data.id === null;
    if (!creating) payload.revision = data.revision;
    data.saving = true;
    $("#product-fields").disabled = true;
    $("#reload-product").disabled = true;
    $("#save-product").textContent = "正在保存";
    message();
    validate();
    try {
      const product = await request(creating ? "/api/products" : `/api/products/${data.id}`, { method: creating ? "POST" : "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      fill(product);
      connection(true);
      if (creating) {
        data.flash = "商品已新建。";
        window.location.hash = `#/products/${product.id}`;
      } else message("商品已保存。");
    } catch (error) {
      if (error.code === "duplicate_model") {
        message("这个型号已被使用，请检查后修改。", true);
        data.touched.add("model");
        $("#product-model-error").textContent = "这个型号已被使用。";
        $("#product-model-error").hidden = false;
        fields.model.setAttribute("aria-invalid", "true");
      } else if (error.code === "revision_conflict") {
        message("商品已在其他页面修改。当前输入已保留，请载入最新资料后再修改。", true);
        $("#reload-product").hidden = false;
      } else if (error.status === 422) message("部分资料格式不正确，请检查后再保存。", true);
      else if (error.status === 404) message("这件商品已无法读取，请返回列表重新选择。", true);
      else { connection(false); message("暂时无法确认保存结果。输入已保留，可以到商品列表核对后再试。", true); }
    } finally {
      data.saving = false;
      $("#product-fields").disabled = false;
      $("#reload-product").disabled = false;
      $("#save-product").textContent = data.id ? "保存修改" : "保存商品";
      // Preserve server validation messages until the user changes an input.
      $("#save-product").disabled = data.id !== null && !dirty();
      $("#product-save-state").textContent = dirty() ? "有未保存的修改" : "与已保存内容一致";
    }
  });
  return { enter, hide, canLeave };
})();
