<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { QaValueField, QaValueFieldGroup } from '@quantumaudio/ableton-extension-sdk/vue'
import type { Vec3 } from '@/types'

const props = defineProps<{
  modelValue: Vec3
  labels?: [string, string, string]
  step?: number
  disabled?: boolean
  /** Axis min/max for QaValueField (required by SDK). */
  min?: number
  max?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [Vec3]
}>()

const labels = computed(() => props.labels || (['X', 'Y', 'Z'] as [string, string, string]))
const min = computed(() => props.min ?? -1e5)
const max = computed(() => props.max ?? 1e5)
const step = computed(() => props.step ?? 0.01)

/** Local draft so drag ticks don't immediately hit the parent. */
const draft = ref<Vec3>([...props.modelValue] as Vec3)

watch(
  () => props.modelValue,
  (v) => {
    draft.value = [...v] as Vec3
  },
)

let timer: ReturnType<typeof setTimeout> | null = null

function flush() {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  const next: Vec3 = [...draft.value] as Vec3
  const cur = props.modelValue
  if (next[0] === cur[0] && next[1] === cur[1] && next[2] === cur[2]) return
  emit('update:modelValue', next)
}

function scheduleCommit() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    timer = null
    flush()
  }, 120)
}

function setAxis(i: number, n: number) {
  const next: Vec3 = [...draft.value] as Vec3
  next[i] = n
  draft.value = next
  scheduleCommit()
}

function onPointerUp() {
  flush()
}

onUnmounted(() => {
  if (timer) clearTimeout(timer)
  flush()
})
</script>

<template>
  <div class="fd-vec3" @pointerup="onPointerUp" @pointercancel="onPointerUp">
    <QaValueFieldGroup>
      <QaValueField
        v-for="(lab, i) in labels"
        :key="lab"
        :model-value="draft[i]"
        :label="lab"
        :min="min"
        :max="max"
        :step="step"
        :default-value="draft[i]"
        :disabled="disabled"
        width="100%"
        @update:model-value="setAxis(i, $event)"
      />
    </QaValueFieldGroup>
  </div>
</template>

<style scoped>
.fd-vec3 {
  width: 100%;
  min-width: 0;
}
/* Override SDK inline-flex / content-sized boxes so axes share full width. */
.fd-vec3 :deep(.qa-value-field-group) {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
}
.fd-vec3 :deep(.qa-value-field-group__bar) {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  width: 100%;
  min-width: 0;
  gap: var(--fd-space-1);
}
.fd-vec3 :deep(.qa-value-field) {
  flex: 1 1 0;
  width: 0; /* equal flex columns; ignore content intrinsic width */
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.fd-vec3 :deep(.qa-value-field__label) {
  flex: 0 0 auto;
}
.fd-vec3 :deep(.qa-value-field__box) {
  display: flex;
  width: 100% !important;
  min-width: 0 !important;
  max-width: none;
  margin-left: 0 !important;
  overflow: hidden;
  text-overflow: ellipsis;
  justify-content: center;
  border-radius: var(--fd-radius-sm) !important;
}
.fd-vec3 :deep(.qa-value-field__input) {
  width: 100%;
  min-width: 0;
}
</style>
