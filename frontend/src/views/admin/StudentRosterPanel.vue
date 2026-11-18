<script setup>
import { computed, onMounted, ref } from 'vue'
import { showToast, showConfirmDialog } from 'vant'
import api, { downloadBlob } from '../../api'
import { GRADE_ORDER, classSortKey, gradeOfClass, normalizeGrade } from '../../constants'

const tab = ref('students')

/* ---------- 学生名册 ---------- */
const students = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const q = ref('')
const filterGrade = ref('')
const filterClass = ref('')
const filterYear = ref('')
const filterGender = ref('')
const registry = ref([])
const loading = ref(false)

const showStudentDialog = ref(false)
const editingStudent = ref(null)
const studentForm = ref({ student_no: '', name: '', gender: '', class_name: '', enrollment_year: null })
const showClassPicker = ref(false)

const classNames = computed(() => registry.value.map((c) => c.name).sort((a, b) => {
  const [ga, ca] = classSortKey(a)
  const [gb, cb] = classSortKey(b)
  return ga - gb || ca - cb
}))
const groupedClasses = computed(() => {
  const map = {}
  for (const c of classNames.value) {
    const g = gradeOfClass(c) || '未分年级'
    ;(map[g] = map[g] || []).push(c)
  }
  return [...GRADE_ORDER, '未分年级'].filter((g) => map[g]).map((g) => ({ grade: g, classes: map[g] }))
})
const years = computed(() => [...new Set(registry.value.map((c) => c.enrollment_year).filter(Boolean))].sort((a, b) => b - a))
const classMeta = computed(() => Object.fromEntries(registry.value.map((c) => [c.name, c])))

async function loadRegistry() {
  const { data } = await api.get('/classes/registry')
  registry.value = data.items
}

async function loadStudents() {
  loading.value = true
  try {
    const { data } = await api.get('/students', {
      params: {
        q: q.value,
        grade: filterGrade.value,
        class_name: filterClass.value,
        enrollment_year: filterYear.value || undefined,
        gender: filterGender.value,
        page: page.value,
        page_size: pageSize
      }
    })
    students.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  loadStudents()
}

function openCreate() {
  editingStudent.value = null
  studentForm.value = {
    student_no: '',
    name: '',
    gender: '',
    class_name: filterClass.value || classNames.value[0] || '',
    enrollment_year: filterYear.value || years.value[0] || null
  }
  showStudentDialog.value = true
}

function openEdit(s) {
  editingStudent.value = s
  studentForm.value = {
    student_no: s.student_no,
    name: s.name,
    gender: s.gender || '',
    class_name: s.class_name,
    enrollment_year: s.enrollment_year
  }
  showStudentDialog.value = true
}

function pickClass(c) {
  studentForm.value.class_name = c
  const meta = classMeta.value[c]
  if (meta?.enrollment_year) studentForm.value.enrollment_year = meta.enrollment_year
  showClassPicker.value = false
}

async function saveStudent() {
  if (!studentForm.value.name.trim()) {
    showToast('请填写姓名')
    return
  }
  if (!studentForm.value.class_name) {
    showToast('请选择班级')
    return
  }
  try {
    const body = { ...studentForm.value }
    body.grade = gradeOfClass(body.class_name)
    if (!body.student_no) delete body.student_no
    if (!body.gender) body.gender = null
    if (!body.enrollment_year) body.enrollment_year = null
    if (editingStudent.value) {
      await api.patch(`/students/${editingStudent.value.id}`, body)
    } else {
      await api.post('/students', body)
    }
    showToast('已保存')
    showStudentDialog.value = false
    await Promise.all([loadStudents(), loadRegistry()])
  } catch {
    /* 拦截器已提示 */
  }
}

async function removeStudent(s) {
  try {
    await showConfirmDialog({ title: '停用学生', message: `确定停用 ${s.name}？（历史点赞保留，可重新导入恢复）` })
    await api.delete(`/students/${s.id}`)
    showToast('已停用')
    await Promise.all([loadStudents(), loadRegistry()])
  } catch {
    /* 取消或拦截器提示 */
  }
}

function exportStudents() {
  downloadBlob('/exports/students.xlsx', '学生名册.xlsx')
}

/* ---------- 班级管理 ---------- */
const classLoading = ref(false)
const showBulkDialog = ref(false)
const bulkForm = ref({
  seventh: { count: 28, year: new Date().getFullYear() },
  eighth: { count: 20, year: new Date().getFullYear() - 1 },
  ninth: { count: 12, year: new Date().getFullYear() - 2 }
})
const showRenameDialog = ref(false)
const renaming = ref(null)
const renameValue = ref('')
const showClassCreate = ref(false)
const newClass = ref({ grade: '七年级', class_no: 1, enrollment_year: new Date().getFullYear() })

async function loadClasses() {
  classLoading.value = true
  try {
    await loadRegistry()
  } finally {
    classLoading.value = false
  }
}

async function createBulkClasses() {
  const items = [
    { grade: '七年级', count: Number(bulkForm.value.seventh.count), enrollment_year: Number(bulkForm.value.seventh.year) || null },
    { grade: '八年级', count: Number(bulkForm.value.eighth.count), enrollment_year: Number(bulkForm.value.eighth.year) || null },
    { grade: '九年级', count: Number(bulkForm.value.ninth.count), enrollment_year: Number(bulkForm.value.ninth.year) || null }
  ].filter((x) => x.count > 0)
  try {
    const { data } = await api.post('/classes/registry/bulk', { items })
    showToast(`新建 ${data.created} 个班，跳过 ${data.skipped} 个已存在班级`)
    showBulkDialog.value = false
    await loadRegistry()
  } catch {
    /* 拦截器已提示 */
  }
}

async function syncFromStudents() {
  try {
    const { data } = await api.post('/classes/registry/sync')
    showToast(`已从学生名册同步 ${data.created} 个班级`)
    await loadRegistry()
  } catch {
    /* 拦截器已提示 */
  }
}

async function createSingleClass() {
  try {
    await api.post('/classes/registry', {
      grade: newClass.value.grade,
      class_no: Number(newClass.value.class_no),
      enrollment_year: Number(newClass.value.enrollment_year) || null
    })
    showToast('班级已创建')
    showClassCreate.value = false
    await loadRegistry()
  } catch {
    /* 拦截器已提示 */
  }
}

function openRename(c) {
  renaming.value = c
  renameValue.value = c.name
  showRenameDialog.value = true
}

async function saveRename() {
  try {
    await api.patch(`/classes/registry/${renaming.value.id}`, { name: renameValue.value.trim() })
    showToast('已重命名')
    showRenameDialog.value = false
    await loadRegistry()
    await loadStudents()
  } catch {
    /* 拦截器已提示 */
  }
}

async function deactivateClass(c) {
  try {
    await showConfirmDialog({
      title: '停用班级',
      message: c.student_count > 0 ? `${c.name} 还有 ${c.student_count} 名学生，请先转班。` : `确定停用 ${c.name}？`
    })
    if (c.student_count > 0) return
    await api.delete(`/classes/registry/${c.id}`)
    showToast('已停用')
    await loadRegistry()
  } catch {
    /* 取消或拦截器提示 */
  }
}

function exportTeaching() {
  downloadBlob('/exports/teaching.xlsx', '任教关系.xlsx')
}

onMounted(async () => {
  await loadRegistry()
  await loadStudents()
})
</script>

<template>
  <div class="roster-panel">
    <van-tabs v-model:active="tab" sticky>
      <van-tab title="学生名册" name="students">
        <div class="toolbar roster-toolbar">
          <van-search v-model="q" placeholder="姓名 / 学号" style="flex: 1; min-width: 150px" @search="applyFilters" @clear="applyFilters" />
          <van-button size="small" type="warning" icon="plus" @click="openCreate">新增学生</van-button>
          <van-button size="small" plain icon="down" @click="exportStudents">导出</van-button>
        </div>
        <div class="roster-filters">
          <select v-model="filterGrade" class="native-select" @change="applyFilters">
            <option value="">全年级</option>
            <option v-for="g in GRADE_ORDER" :key="g" :value="g">{{ g }}</option>
          </select>
          <select v-model="filterClass" class="native-select" @change="applyFilters">
            <option value="">全部班级</option>
            <option v-for="c in classNames" :key="c" :value="c">{{ c }}</option>
          </select>
          <select v-model="filterYear" class="native-select" @change="applyFilters">
            <option value="">全部级</option>
            <option v-for="y in years" :key="y" :value="y">{{ y }}级</option>
          </select>
          <select v-model="filterGender" class="native-select" @change="applyFilters">
            <option value="">性别</option>
            <option value="男">男</option>
            <option value="女">女</option>
          </select>
        </div>

        <div class="roster-summary">共 {{ total }} 人 · 第 {{ page }} 页</div>
        <van-loading v-if="loading" style="text-align: center; padding: 24px" />
        <van-cell-group v-else inset>
          <van-cell
            v-for="s in students"
            :key="s.id"
            :title="`${s.name}（${s.student_no}）`"
            :label="`${s.class_name} · ${s.gender || '未填性别'} · ${s.enrollment_year ? s.enrollment_year + '级' : '未填级'}`"
            is-link
            @click="openEdit(s)"
          >
            <template #right-icon>
              <van-button size="mini" plain type="danger" icon="delete-o" @click.stop="removeStudent(s)" />
            </template>
          </van-cell>
        </van-cell-group>
        <van-empty v-if="!loading && !students.length" description="没有匹配的学生" />
        <van-pagination
          v-if="total > pageSize"
          v-model="page"
          :total-items="total"
          :items-per-page="pageSize"
          :show-page-size="3"
          force-ellipses
          style="margin: 12px 16px"
          @change="loadStudents"
        />
      </van-tab>

      <van-tab title="班级管理" name="classes">
        <div class="toolbar roster-toolbar">
          <van-button size="small" type="warning" icon="plus" @click="showBulkDialog = true">按数量批量建班</van-button>
          <van-button size="small" plain @click="showClassCreate = true">新增班级</van-button>
          <van-button size="small" plain @click="syncFromStudents">从学生名册同步</van-button>
          <van-button size="small" plain icon="down" @click="exportTeaching">导出任教</van-button>
        </div>
        <div class="muted" style="padding: 0 16px 8px">
          建议先按 七年级 28 个班、八年级 20 个班、九年级 12 个班建好；空班也可以先指派教师。
        </div>
        <van-loading v-if="classLoading" style="text-align: center; padding: 24px" />
        <div v-else class="class-registry-grid">
          <div v-for="g in GRADE_ORDER" :key="g" class="class-registry-grade">
            <div class="class-registry-title">{{ g }}</div>
            <div class="class-registry-list">
              <div v-for="c in registry.filter((x) => normalizeGrade(x.grade) === g)" :key="c.name" class="class-registry-item" :class="{ empty: !c.student_count }">
                <div class="class-registry-name">{{ c.name }}</div>
                <div class="class-registry-meta">
                  <span>{{ c.student_count }} 人</span>
                  <span v-if="c.enrollment_year">{{ c.enrollment_year }}级</span>
                  <span v-if="!c.registered" class="warn">未登记</span>
                </div>
                <div class="class-registry-actions">
                  <van-button v-if="c.id" size="mini" plain icon="edit" @click="openRename(c)">改名</van-button>
                  <van-button v-if="c.id" size="mini" plain type="danger" icon="delete-o" @click="deactivateClass(c)">停用</van-button>
                </div>
              </div>
            </div>
          </div>
        </div>
        <van-empty v-if="!registry.length" description="还没有班级，点上方按钮建班或导入学生" />
      </van-tab>
    </van-tabs>

    <!-- 学生编辑 -->
    <van-dialog teleport="body" v-model:show="showStudentDialog" :title="editingStudent ? '编辑学生' : '新增学生'" show-cancel-button class="form-dialog" @confirm="saveStudent">
      <van-field v-model="studentForm.student_no" label="学号" placeholder="留空自动生成" :disabled="!!editingStudent" />
      <van-field v-model="studentForm.name" label="姓名" placeholder="必填" />
      <van-field label="性别">
        <template #input>
          <van-radio-group v-model="studentForm.gender" direction="horizontal">
            <van-radio name="男">男</van-radio>
            <van-radio name="女">女</van-radio>
          </van-radio-group>
        </template>
      </van-field>
      <van-field
        :model-value="studentForm.class_name"
        label="班级"
        placeholder="点击选择"
        is-link
        readonly
        @click="showClassPicker = true"
      />
      <van-field v-model.number="studentForm.enrollment_year" label="级（入学年份）" type="digit" placeholder="如：2026" />
    </van-dialog>

    <!-- 班级选择 -->
    <van-popup teleport="body" v-model:show="showClassPicker" position="bottom" round>
      <div class="class-picker-panel">
        <div class="class-picker-title">选择班级</div>
        <div class="class-picker-list">
          <div v-for="g in groupedClasses" :key="g.grade" class="class-picker-grade">
            <span class="grade-label">{{ g.grade }}</span>
            <div class="class-picker-inline" style="max-height: none">
              <button
                v-for="c in g.classes"
                :key="c"
                type="button"
                class="class-toggle"
                :class="{ on: studentForm.class_name === c }"
                @click="pickClass(c)"
              >
                {{ c }}
              </button>
            </div>
          </div>
          <van-empty v-if="!classNames.length" description="还没有班级，请先在班级管理中建班" />
        </div>
      </div>
    </van-popup>

    <!-- 批量建班 -->
    <van-dialog teleport="body" v-model:show="showBulkDialog" title="按数量批量建班" show-cancel-button class="form-dialog" @confirm="createBulkClasses">
      <div class="bulk-row">
        <span>七年级</span>
        <van-field v-model.number="bulkForm.seventh.count" type="digit" label="班数" />
        <van-field v-model.number="bulkForm.seventh.year" type="digit" label="级" />
      </div>
      <div class="bulk-row">
        <span>八年级</span>
        <van-field v-model.number="bulkForm.eighth.count" type="digit" label="班数" />
        <van-field v-model.number="bulkForm.eighth.year" type="digit" label="级" />
      </div>
      <div class="bulk-row">
        <span>九年级</span>
        <van-field v-model.number="bulkForm.ninth.count" type="digit" label="班数" />
        <van-field v-model.number="bulkForm.ninth.year" type="digit" label="级" />
      </div>
      <div class="muted" style="padding: 8px 16px">班级名自动生成，如“七年级1班”；已存在的班级会跳过。</div>
    </van-dialog>

    <!-- 新增班级 -->
    <van-dialog teleport="body" v-model:show="showClassCreate" title="新增班级" show-cancel-button class="form-dialog" @confirm="createSingleClass">
      <van-field label="年级">
        <template #input>
          <select v-model="newClass.grade" class="native-select">
            <option v-for="g in GRADE_ORDER" :key="g" :value="g">{{ g }}</option>
          </select>
        </template>
      </van-field>
      <van-field v-model.number="newClass.class_no" type="digit" label="班号" placeholder="如：1" />
      <van-field v-model.number="newClass.enrollment_year" type="digit" label="级" placeholder="如：2026" />
    </van-dialog>

    <!-- 班级改名 -->
    <van-dialog teleport="body" v-model:show="showRenameDialog" title="班级改名" show-cancel-button class="form-dialog" @confirm="saveRename">
      <van-field v-model="renameValue" label="班级名" placeholder="如：七年级1班" />
      <div class="muted" style="padding: 8px 16px">改名会同步该班学生、小组和任教关系。</div>
    </van-dialog>
  </div>
</template>