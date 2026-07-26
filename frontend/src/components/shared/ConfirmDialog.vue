<script setup lang="ts">
import { QaButton, QaDialog } from '@quantumaudio/ableton-extension-sdk/vue'
import { useUiChrome } from '@/composables/useUiChrome'

const ui = useUiChrome()
</script>

<template>
  <QaDialog
    v-if="ui.state.confirm"
    :open="!!ui.state.confirm"
    :title="ui.state.confirm.title"
    @close="ui.resolveConfirm(false)"
  >
    <template #default>
      <p>{{ ui.state.confirm.message }}</p>
    </template>
    <template #footer>
      <QaButton @click="ui.resolveConfirm(false)">Cancel</QaButton>
      <QaButton
        :accent="ui.state.confirm.danger ? 'red' : true"
        @click="ui.resolveConfirm(true)"
      >
        Confirm
      </QaButton>
    </template>
  </QaDialog>
</template>
