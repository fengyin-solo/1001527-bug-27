<template>
  <section class="page" data-module="fault">
    <header class="page-head">
      <div>
        <h2>故障处置管理</h2>
        <p class="page-desc">登记故障并按站点区域排列处置视图；挂起与恢复分别记录原因与时刻，重复报障按同站点同现象自动合并。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记故障记录</button>
        <button class="btn" type="button" @click="exportRows">导出故障处置清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in boardCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>故障编号/站点/区域</span>
        <input v-model="filters.keyword" placeholder="按故障编号、涉及站点或区域检索" />
      </label>
      <label class="filter-item">
        <span>故障状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>站点区域</span>
        <select v-model="filters.region">
          <option value="">全部区域</option>
          <option v-for="region in regions" :key="region" :value="region">{{ region }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>排列方式</span>
        <select v-model="filters.sort">
          <option value="">按报障先后</option>
          <option value="region">按站点区域排列</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>明细</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '故障状态'">
              <span class="status-badge" :class="statusClass(String(row[column]))">{{ row[column] }}</span>
            </template>
            <template v-else-if="column === '影响要素'">
              {{ row[column] || '—' }}
              <span v-if="!row[column]" class="warn-tag" title="影响要素未填，处置前需补全">待补影响要素</span>
            </template>
            <template v-else-if="column === '挂起原因'">
              <span :title="String(row[column] ?? '')">{{ row[column] ? '有挂起记录' : '—' }}</span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td><button class="link" type="button" @click="openDetail(row)">查看详情</button></td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="openAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row).length" class="muted-text">无</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无符合条件的故障记录，可先登记故障记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条故障处置记录</span>
      <span v-if="message" :class="messageOk ? 'success-text' : 'error-text'">{{ message }}</span>
    </footer>

    <!-- 登记故障 -->
    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>登记故障记录</h3>
        <p class="modal-tip">同一站点、同一故障现象且尚未恢复时，系统会自动合并为重复报障，不另建记录。</p>
        <label class="form-item"><span>故障编号 *</span><input v-model="createForm.故障编号" /></label>
        <label class="form-item"><span>涉及站点 *</span><input v-model="createForm.涉及站点" list="station-names" /></label>
        <label class="form-item"><span>站点区域 *</span><input v-model="createForm.站点区域" list="region-names" placeholder="如：西南片区" /></label>
        <label class="form-item"><span>故障现象 *</span><input v-model="createForm.故障现象" /></label>
        <label class="form-item"><span>影响要素 *</span><input v-model="createForm.影响要素" placeholder="如：气温、雨量" /></label>
        <label class="form-item"><span>发生时刻</span><input v-model="createForm.发生时刻" placeholder="留空取当前时刻" /></label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitCreate">提交登记</button>
        </div>
      </div>
    </div>
    <datalist id="station-names">
      <option v-for="name in stationNames" :key="name" :value="name" />
    </datalist>
    <datalist id="region-names">
      <option v-for="region in regions" :key="region" :value="region" />
    </datalist>

    <!-- 处置动作 -->
    <div v-if="actionVisible" class="modal-mask" @click.self="closeAction">
      <div class="modal">
        <h3>{{ actionForm.action }} · {{ actionRow?.故障编号 }}</h3>
        <p class="modal-tip" v-if="actionForm.action === '挂起故障'">挂起后故障仍计入异常量；挂起原因与时刻会保留，恢复时不丢失。</p>
        <p class="modal-tip" v-else-if="actionForm.action === '确认恢复'">恢复时刻自动记录；若故障此前挂起，挂起原因会继续保留在明细里。</p>
        <p class="modal-tip" v-else>派单后故障进入处置中并计入异常量，处置时长自派单时刻起算。</p>
        <label v-if="actionForm.action === '派单处置'" class="form-item">
          <span>处置人员 *</span><input v-model="actionForm.处置人员" />
        </label>
        <template v-if="actionForm.action === '挂起故障'">
          <label class="form-item"><span>挂起原因 *</span><textarea v-model="actionForm.挂起原因" rows="3"></textarea></label>
        </template>
        <label v-if="actionForm.action === '确认恢复'" class="form-item">
          <span>恢复说明</span><textarea v-model="actionForm.恢复说明" rows="3" placeholder="可填写处置措施，选填"></textarea>
        </label>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeAction">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitAction">确认</button>
        </div>
      </div>
    </div>

    <!-- 故障明细 -->
    <div v-if="detailVisible" class="modal-mask" @click.self="closeDetail">
      <div class="modal modal-wide">
        <h3>故障明细 · {{ detail?.故障编号 }}</h3>
        <p v-if="detail && !detail.信息完整" class="warn-text">资料未齐：{{ detail.待补字段 }}，请补全后再继续处置。</p>
        <table v-if="detail" class="detail-table">
          <tbody>
            <tr v-for="field in detailFields" :key="field">
              <th>{{ field }}</th><td>{{ detail[field] || '—' }}</td>
            </tr>
            <tr><th>报障次数</th><td>{{ detail.报障次数 }} 次（含重复报障合并）</td></tr>
            <tr><th>异常标识</th><td>{{ detail.异常标识 }}</td></tr>
            <tr><th>处置时长</th><td>{{ detail.处置时长 }}</td></tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BoardCard = { label: string; value: string | number }

const ENDPOINT = '/api/fault'
const columns = ["故障编号", "涉及站点", "站点区域", "故障现象", "发生时刻", "影响要素", "处置人员", "派单时刻", "挂起时刻", "挂起原因", "恢复时刻", "处置时长", "故障状态"]
const detailFields = ["故障编号", "涉及站点", "站点区域", "故障现象", "发生时刻", "影响要素", "处置人员", "派单时刻", "挂起时刻", "挂起原因", "恢复时刻", "恢复说明", "故障状态"]
const statuses = ["待派单", "处置中", "已挂起", "已恢复"]

const rows = ref<Row[]>([])
const total = ref(0)
const message = ref('')
const messageOk = ref(false)
const regions = ref<string[]>([])
const boardCards = ref<BoardCard[]>([])
const filters = ref<Record<string, string>>({ keyword: '', status: '', region: '', sort: '' })

const submitting = ref(false)
const createVisible = ref(false)
const createForm = ref<Record<string, string>>({
  故障编号: '', 涉及站点: '', 站点区域: '', 故障现象: '', 影响要素: '', 发生时刻: '',
})

const actionVisible = ref(false)
const actionRow = ref<Row | null>(null)
const actionForm = ref<Record<string, string>>({ action: '', 处置人员: '', 挂起原因: '', 恢复说明: '' })

const detailVisible = ref(false)
const detail = ref<Row | null>(null)

const stationNames = computed(() => Array.from(new Set(rows.value.map((row) => String(row.涉及站点 ?? '')).filter(Boolean))))

function setMessage(text: string, ok: boolean) {
  message.value = text
  messageOk.value = ok
}

function availableActions(row: Row): string[] {
  switch (String(row.故障状态)) {
    case '待派单':
      return ['派单处置']
    case '处置中':
      return ['挂起故障', '确认恢复']
    case '已挂起':
      return ['确认恢复']
    default:
      return []
  }
}

function statusClass(status: string): string {
  return {
    待派单: 'st-pending',
    处置中: 'st-active',
    已挂起: 'st-suspended',
    已恢复: 'st-recovered',
  }[status] ?? ''
}

function resetFilters() {
  filters.value = { keyword: '', status: '', region: '', sort: '' }
  void reload()
}

function exportRows() {
  const query = new URLSearchParams(
    Object.fromEntries(Object.entries(filters.value).filter(([, value]) => value)),
  ).toString()
  window.open(`${ENDPOINT}/export?${query}`, '_blank')
}

function openCreate() {
  createForm.value = { 故障编号: '', 涉及站点: '', 站点区域: '', 故障现象: '', 影响要素: '', 发生时刻: '' }
  createVisible.value = true
}

function closeCreate() {
  createVisible.value = false
}

async function submitCreate() {
  setMessage('', true)
  submitting.value = true
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      setMessage(payload.message ?? '故障记录登记未生效，请稍后重试', false)
      return
    }
    closeCreate()
    setMessage(payload.message, true)
    await Promise.all([reload(), loadBoard()])
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '故障记录登记失败', false)
  } finally {
    submitting.value = false
  }
}

function openAction(action: string, row: Row) {
  actionRow.value = row
  actionForm.value = {
    action,
    处置人员: String(row.处置人员 ?? ''),
    挂起原因: '',
    恢复说明: '',
  }
  actionVisible.value = true
}

function closeAction() {
  actionVisible.value = false
  actionRow.value = null
}

async function submitAction() {
  if (!actionRow.value) return
  setMessage('', true)
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/${actionRow.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...actionForm.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      setMessage(payload.message ?? '故障处置动作未生效，请稍后重试', false)
      return
    }
    closeAction()
    setMessage(payload.message, true)
    await Promise.all([reload(), loadBoard()])
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '故障处置操作失败', false)
  } finally {
    submitting.value = false
  }
}

async function openDetail(row: Row) {
  detail.value = null
  detailVisible.value = true
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('故障明细读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '故障明细读取失败', false)
    detailVisible.value = false
  }
}

function closeDetail() {
  detailVisible.value = false
  detail.value = null
}

async function loadBoard() {
  try {
    const response = await request(`${ENDPOINT}/board?${new URLSearchParams(
      Object.fromEntries(Object.entries({ region: filters.value.region }).filter(([, value]) => value)),
    )}`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    boardCards.value = payload.cards ?? []
    regions.value = payload.regions ?? []
  } catch {
    // 看板加载失败不阻塞列表
  }
}

async function reload() {
  setMessage('', true)
  const query = new URLSearchParams(
    Object.fromEntries(Object.entries(filters.value).filter(([, value]) => value)),
  ).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('故障记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await loadBoard()
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '故障处置列表读取失败', false)
  }
}

onMounted(reload)
</script>

<style scoped>
.status-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.st-pending { background: #f2f4f7; color: #475467; border-color: #d0d5dd; }
.st-active { background: #fff4e5; color: #b54708; border-color: #fdb022; }
.st-suspended { background: #fef3f2; color: #b42318; border-color: #fda29b; }
.st-recovered { background: #ecfdf3; color: #027a48; border-color: #6ce9a6; }
.warn-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 12px;
  background: #fffaeb;
  color: #b54708;
  border: 1px solid #fedf89;
}
.muted-text { color: var(--muted); font-size: 12px; }
.success-text { color: #027a48; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  width: 460px;
  max-height: 86vh;
  overflow-y: auto;
}
.modal-wide { width: 620px; }
.modal h3 { margin: 0 0 8px; font-size: 16px; }
.modal-tip { font-size: 12px; color: var(--muted); margin: 0 0 10px; }
.form-item { display: block; margin-bottom: 10px; font-size: 13px; }
.form-item span { display: block; color: var(--muted); margin-bottom: 4px; }
.form-item input, .form-item textarea {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font: inherit;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.detail-table { width: 100%; border-collapse: collapse; }
.detail-table th, .detail-table td {
  border: 1px solid var(--border);
  padding: 6px 10px;
  font-size: 13px;
  text-align: left;
}
.detail-table th { width: 110px; background: #f9fafb; color: var(--muted); }
.warn-text { color: #b42318; font-size: 13px; }
</style>
