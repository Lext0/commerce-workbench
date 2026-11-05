"use strict";

const DistributionUI = (() => {
  const $ = selector => document.querySelector(selector);
  const json = (method, value = {}) => ({ method, headers: {"Content-Type":"application/json"}, body: JSON.stringify(value) });
  const node = (tag, text) => { const el = document.createElement(tag); el.textContent = text; return el; };
  const button = (text, action) => { const el = node('button', text); el.type = 'button'; el.className = 'button button-small'; el.addEventListener('click', action); return el; };
  let currentBatch = null;

  async function search() {
    const list = $('#distribution-products');
    list.replaceChildren(node('li', '正在查找…'));
    try {
      const result = await request('/api/products?' + new URLSearchParams({q: $('#distribution-search').value.trim(), limit: 100}));
      list.replaceChildren();
      if (!result.items.length) list.append(node('li', '没有找到商品。'));
      for (const p of result.items) {
        const li = node('li', `${p.name}（${p.model}）`);
        li.append(button('加入清单', async () => {
          try { await request('/api/distribution/queue', json('POST', {product_id:p.id})); await loadQueue(); }
          catch (e) { $('#distribution-queue-message').textContent = e.message; }
        }));
        li.append(button('复制商品', async () => {
          const model = window.prompt('输入新商品型号'); if (model === null) return;
          try { await request(`/api/distribution/copy/${p.id}`, json('POST', {model})); await loadQueue(); $('#distribution-queue-message').textContent = '已复制商品并加入清单。'; }
          catch (e) { $('#distribution-queue-message').textContent = e.message; }
        }));
        list.append(li);
      }
      if (result.total > result.items.length) list.append(node('li', '仅显示前 100 件，请输入更具体的关键词。'));
    } catch (e) { list.replaceChildren(node('li', `读取失败：${e.message}`)); }
  }

  async function loadQueue() {
    const list = $('#distribution-queue');
    try {
      const products = await request('/api/distribution/queue'); list.replaceChildren();
      if (!products.length) list.append(node('li', '清单为空。'));
      for (const p of products) {
        const li = document.createElement('li');
        const box = document.createElement('input'); box.type = 'checkbox'; box.checked = Boolean(p.selected); box.setAttribute('aria-label', `选择 ${p.name}`);
        box.addEventListener('change', async () => { try { await request(`/api/distribution/queue/${p.id}`, json('PUT', {selected:box.checked})); } catch (e) { box.checked = !box.checked; $('#distribution-queue-message').textContent = e.message; } });
        const link = node('a', `${p.name}（${p.model}）`); link.href = `#/products/${p.id}`;
        li.append(box, link, node('span', p.price_cents == null ? '未设售价' : `¥ ${(p.price_cents / 100).toFixed(2)}`));
        li.append(button('移除', async () => { try { await request(`/api/distribution/queue/${p.id}`, json('DELETE')); await loadQueue(); } catch(e) { $('#distribution-queue-message').textContent = e.message; } }));
        list.append(li);
      }
    } catch(e) { list.replaceChildren(node('li', `读取失败：${e.message}`)); }
  }

  async function loadBatches() {
    const list = $('#distribution-batches');
    try {
      const batches = await request('/api/distribution/batches'); list.replaceChildren();
      if (!batches.length) list.append(node('li', '暂无批次记录。'));
      for (const b of batches) { const li = document.createElement('li'); li.append(button(`批次 ${b.id} · ${formatDate(b.created_at)}`, () => loadBatch(b.id))); list.append(li); }
    } catch(e) { list.replaceChildren(node('li', `读取失败：${e.message}`)); }
  }

  async function loadBatch(id) {
    try {
      const batch = await request(`/api/distribution/batches/${id}`); currentBatch = id;
      const container = $('#distribution-batch-detail'); container.replaceChildren(node('h3', `批次 ${id}`));
      const list = document.createElement('ul');
      const labels = {pending:'待处理', success:'成功', failed:'失败', skipped:'已跳过'};
      for (const item of batch.items) {
        const li = node('li', `${item.name}（${item.model}）：${labels[item.status]} ${item.message}`);
        if (item.status === 'failed' || item.status === 'pending') {
          const link = node('a', '修改商品'); link.href = `#/products/${item.product_id}`; li.append(link);
          li.append(button('重试', async () => {
            try { await request(`/api/distribution/batches/${id}/items/${item.product_id}/retry`, json('POST')); await loadBatch(id); }
            catch(e) { $('#distribution-batch-message').textContent = `重试失败：${e.message}`; }
          }));
        }
        list.append(li);
      }
      container.append(list);
    } catch(e) { $('#distribution-batch-message').textContent = `读取失败：${e.message}`; }
  }

  $('#distribution-search-form').addEventListener('submit', e => { e.preventDefault(); search(); });
  $('#distribution-import').addEventListener('click', async () => {
    const file = $('#distribution-csv').files[0]; const message = $('#distribution-import-message');
    if (!file || file.size > 1000000) { message.textContent = '请选择不超过 1 MB 的 CSV 文件。'; return; }
    const btn = $('#distribution-import'); btn.disabled = true;
    try {
      const text = new TextDecoder('utf-8', {fatal:true}).decode(await file.arrayBuffer());
      const result = await request('/api/distribution/import', json('POST', {text}));
      const list = $('#distribution-import-results'); list.replaceChildren();
      for (const row of result.rows) list.append(node('li', `第 ${row.line} 行：${row.status === 'imported' ? '已导入' : row.message}`));
      message.textContent = `导入 ${result.rows.filter(r => r.status === 'imported').length} 条，失败 ${result.rows.filter(r => r.status === 'error').length} 条。`;
      await loadQueue();
    } catch(e) { message.textContent = `导入失败：${e.message}`; }
    finally { btn.disabled = false; }
  });
  $('#distribution-publish').addEventListener('click', async () => {
    if (!window.confirm('确认将选中的商品发布到本地模拟店铺？')) return;
    const btn = $('#distribution-publish'); btn.disabled = true;
    let requestId = sessionStorage.getItem('distribution-request-id');
    if (!requestId) { requestId = crypto.randomUUID(); sessionStorage.setItem('distribution-request-id', requestId); }
    try {
      const result = await request('/api/distribution/batches', json('POST', {request_id:requestId}));
      sessionStorage.removeItem('distribution-request-id'); $('#distribution-batch-message').textContent = '批次已处理，请查看逐件结果。';
      await loadBatches(); await loadBatch(result.id);
    } catch(e) {
      if (e.status && e.status < 500) sessionStorage.removeItem('distribution-request-id');
      $('#distribution-batch-message').textContent = `暂时无法确认批次结果：${e.message}。可再次点击以恢复。`;
    } finally { btn.disabled = false; }
  });
  $('#distribution-refresh').addEventListener('click', async () => { await loadBatches(); if (currentBatch) await loadBatch(currentBatch); });
  $('#distribution-quote-form').addEventListener('submit', async e => {
    e.preventDefault();
    const payload = Object.fromEntries(['cost','shipping','exchange','fee','profit'].map(key => [key, $(`#quote-${key}`).value.trim()]));
    try { const result = await request('/api/distribution/quote', json('POST', payload)); $('#distribution-quote-result').textContent = `参考报价：$${result.usd} / 件`; }
    catch(error) { $('#distribution-quote-result').textContent = error.message; }
  });
  function enter() { search(); loadQueue(); loadBatches(); }
  return { enter };
})();
