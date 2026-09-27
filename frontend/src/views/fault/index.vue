<template>
  <section class="page" data-module="fault">
    <header class="page-head">
      <div>
        <h2>故障处置管理</h2>
        <p class="page-desc">登记、派单、挂起与恢复故障记录；同一站点同一故障现象的重复报障自动合并，挂起与恢复均保留原因与时间。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记故障记录</button>
        <button class="btn" type="button" @click="exportRows">导出故障处置清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>故障编号</span>
        <input v-model="filters.keyword" placeholder="按故障编号检索" />
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
        <select v-model="sortMode">
          <option value="">默认排列</option>
          <option value="站点区域">按站点区域排列</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>标记</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="item in displayRows" :key="item.key">
          <tr v-if="item.type === 'group'" class="group-row">
            <td :colspan="columns.length + 2">站点区域：{{ item.region }}（{{ item.count }} 条）</td>
          </tr>
          <tr v-else :class="{ 'row-void': item.row['故障状态'] === '已作废' }">
            <td v-for="column in columns" :key="column">
              <span v-if="column === '影响要素' && item.row['资料待补']" class="tag warn">待补</span>
              {{ displayCell(item.row, column) }}
            </td>
            <td>
              <span v-if="Number(item.row['报障次数'] || 1) > 1" class="tag">重复报障×{{ item.row['报障次数'] }}</span>
              <span v-if="item.row['资料待补']" class="tag warn">影响要素待补</span>
            </td>
            <td class="row-actions">
              <button class="link" type="button" @click="openDetail(item.row)">详情</button>
              <button
                v-for="action in rowActions(item.row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, item.row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
        </template>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无故障处置数据，可先登记故障记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条故障处置记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal">
        <h3>登记故障记录</h3>
        <p class="modal-tip">同一站点同一故障现象的未闭环记录会自动合并，不重复建档。</p>
        <label v-for="field in createFields" :key="field.name" class="modal-field">
          <span>{{ field.label }}<em v-if="field.required" class="required-mark">*</em></span>
          <input v-model="createForm[field.name]" :placeholder="field.placeholder" />
        </label>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitCreate">提交登记</button>
          <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
        </div>
      </div>
    </div>

    <div v-if="reasonDialog.visible" class="modal-mask" @click.self="reasonDialog.visible = false">
      <div class="modal">
        <h3>{{ reasonDialog.action }} · {{ reasonDialog.code }}</h3>
        <p class="modal-tip">{{ reasonDialog.tip }}</p>
        <label class="modal-field">
          <span>{{ reasonDialog.label }}<em v-if="reasonDialog.required" class="required-mark">*</em></span>
          <textarea v-model="reasonDialog.reason" rows="3" :placeholder="reasonDialog.placeholder"></textarea>
        </label>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitReason">确认{{ reasonDialog.action }}</button>
          <button class="btn ghost" type="button" @click="reasonDialog.visible = false">取消</button>
        </div>
      </div>
    </div>

    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <h3>故障详情 · {{ detail['故障编号'] }}</h3>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ displayCell(detail, field) }}</dd>
          </template>
        </dl>
        <h4 class="trace-title">处置轨迹</h4>
        <ul class="trace-list">
          <li v-for="(trace, index) in detailTraces" :key="index">
            <span class="trace-time">{{ trace['时刻'] }}</span>
            <span class="trace-action">{{ trace['动作'] }}</span>
            <span v-if="trace['说明']">{{ trace['说明'] }}</span>
          </li>
          <li v-if="!detailTraces.length" class="empty-state">暂无处置轨迹</li>
        </ul>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null | TraceItem[]>
type TraceItem = { 时刻?: string; 动作?: string; 说明?: string }
type DisplayItem =
  | { type: 'row'; key: string; row: Row }
  | { type: 'group'; key: string; region: string; count: number }

const ENDPOINT = '/api/fault'
const columns = ["故障编号", "涉及站点", "站点区域", "故障现象", "发生时刻", "影响要素", "处置人员", "恢复时刻", "处置时长", "故障状态"]
const statuses = ["待派单", "处置中", "已挂起", "已恢复", "已作废"]
const detailFields = ["故障编号", "涉及站点", "站点区域", "故障现象", "发生时刻", "影响要素", "处置人员", "恢复时刻", "处置时长", "故障状态", "挂起原因", "挂起时刻", "误报原因", "报障次数", "最近报障时刻"]
const createFields = [
  { name: '涉及站点', label: '涉及站点', required: true, placeholder: '如 STAT-0001 城北国家基本站' },
  { name: '站点区域', label: '站点区域', required: false, placeholder: '如 城北片区' },
  { name: '故障现象', label: '故障现象', required: true, placeholder: '如 雨量传感器无数据上传' },
  { name: '发生时刻', label: '发生时刻', required: false, placeholder: 'YYYY-MM-DD HH:MM，留空取当前时间' },
  { name: '影响要素', label: '影响要素', required: false, placeholder: '如 降水；留空会标记为资料待补' },
  { name: '处置人员', label: '处置人员', required: false, placeholder: '可后补' },
]
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  待派单: ["派单处置", "挂起故障", "标记误报"],
  处置中: ["确认恢复", "挂起故障", "标记误报"],
  已挂起: ["派单处置", "确认恢复", "标记误报"],
}

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Record<string, number | string | string[]>>({})
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref({ keyword: '', status: '', region: '' })
const sortMode = ref('')
const createVisible = ref(false)
const createForm = ref<Record<string, string>>({})
const detail = ref<Row | null>(null)
const reasonDialog = ref({
  visible: false,
  action: '',
  code: '',
  rowId: 0,
  label: '',
  tip: '',
  placeholder: '',
  required: false,
  reason: '',
})

const regions = computed(() => (stats.value['站点区域列表'] as string[] | undefined) ?? [])
const statCards = computed(() => [
  { label: '待派单故障', value: stats.value['待派单'] ?? 0 },
  { label: '处置中故障', value: stats.value['处置中'] ?? 0 },
  { label: '异常挂起（异常量）', value: stats.value['异常量'] ?? 0 },
  { label: '资料待补', value: stats.value['资料待补'] ?? 0 },
  { label: '平均处置时长', value: stats.value['平均处置时长'] ?? '—' },
])
const detailTraces = computed(() => {
  const traces = detail.value?.['处置轨迹']
  return Array.isArray(traces) ? (traces as TraceItem[]) : []
})
const displayRows = computed<DisplayItem[]>(() => {
  const items: DisplayItem[] = []
  let lastRegion: string | null = null
  for (const row of rows.value) {
    if (sortMode.value === '站点区域') {
      const region = String(row['站点区域'] || '未填写区域')
      if (region !== lastRegion) {
        items.push({
          type: 'group',
          key: `group-${region}`,
          region,
          count: rows.value.filter((item) => String(item['站点区域'] || '未填写区域') === region).length,
        })
        lastRegion = region
      }
    }
    items.push({ type: 'row', key: `row-${String(row.id)}`, row })
  }
  return items
})

function displayCell(row: Row, column: string): string {
  const value = row[column]
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return String(value)
}

function rowActions(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row['故障状态'] || '')] ?? []
}

function resetFilters() {
  filters.value = { keyword: '', status: '', region: '' }
  sortMode.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  createVisible.value = true
}

async function submitCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.detail || '故障记录登记失败')
    }
    createVisible.value = false
    noticeMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '故障记录登记失败'
  }
}

function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '挂起故障') {
    reasonDialog.value = {
      visible: true,
      action,
      code: String(row['故障编号'] || ''),
      rowId: Number(row.id),
      label: '挂起原因',
      tip: '挂起后该记录计入处置看板异常量，原因与时间会保留在处置轨迹里。',
      placeholder: '如：待备件到货、需厂家远程支持',
      required: true,
      reason: '',
    }
    return
  }
  if (action === '标记误报') {
    reasonDialog.value = {
      visible: true,
      action,
      code: String(row['故障编号'] || ''),
      rowId: Number(row.id),
      label: '误报说明',
      tip: '误报记录将作废，不再计入待处理、异常量与处置时长统计。',
      placeholder: '如：值班员点错故障记录',
      required: false,
      reason: '',
    }
    return
  }
  if (action === '确认恢复') {
    const hint = row['资料待补']
      ? `该记录影响要素未填写，恢复后仍会标记为资料待补。确认将 ${row['故障编号']} 标记为已恢复？`
      : `确认将 ${row['故障编号']} 标记为已恢复？`
    if (!window.confirm(hint)) {
      return
    }
  }
  void postAction(action, Number(row.id))
}

async function submitReason() {
  const dialog = reasonDialog.value
  const reason = dialog.reason.trim()
  if (dialog.required && !reason) {
    errorMessage.value = `${dialog.action}必须填写${dialog.label}`
    return
  }
  dialog.visible = false
  await postAction(dialog.action, dialog.rowId, { 挂起原因: reason, 原因: reason })
}

async function postAction(action: string, rowId: number, extra: Record<string, string> = {}) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${rowId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...extra } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.detail || '故障处置动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '故障处置操作失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('故障详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '故障详情读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  if (filters.value.region) query.set('region', filters.value.region)
  if (sortMode.value) query.set('sort', sortMode.value)
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('故障记录列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      stats.value = await statsResponse.json()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '故障处置列表读取失败'
  }
}

onMounted(reload)
</script>
