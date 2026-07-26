<script setup lang="ts">
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'

defineProps<{
  session: FourdesignerSession
}>()
</script>

<template>
  <div v-if="!session.daemonOk" class="fd-hero" data-testid="fd-hero">
    <h1>4designer</h1>
    <p>Daemon not reachable on port 9983.</p>
    <p class="muted">Start with <code>python -m fourdesigner_daemon</code> or pulse Ensure on the hub.</p>
  </div>
  <div v-else-if="!(session.workspaces || []).length" class="fd-hero soft" data-testid="fd-hero">
    <h1>Waiting for a TD hub</h1>
    <p>Daemon is up. Open a project with the 4designer hub and pulse Ensure Daemon.</p>
  </div>
  <div v-else-if="!session.tdOk" class="fd-hero soft" data-testid="fd-hero">
    <h1>Workspace offline</h1>
    <p>Selected TouchDesigner hub is disconnected. Switch workspace or reconnect the hub WebSocket.</p>
  </div>
  <div
    v-else-if="session.viewMode === 'marshaled' && session.objectCount === 0"
    class="fd-hero soft"
    data-testid="fd-hero"
  >
    <h1>No objects</h1>
    <p>Activate a Marshal COMP (In POP → transform → Out) to register geometry.</p>
  </div>
</template>

<style scoped>
.fd-hero {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 72px 24px 24px;
  background: rgba(14, 15, 18, 0.92);
  text-align: center;
  pointer-events: none;
}
.fd-hero.soft {
  background: rgba(14, 15, 18, 0.72);
}
.fd-hero h1 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--fd-accent);
}
.fd-hero p {
  margin: 4px 0;
  max-width: 420px;
  font-size: var(--fd-font-ui);
}
.muted {
  color: var(--fd-muted);
  font-size: var(--fd-font-micro);
}
code {
  color: var(--fd-accent);
}
</style>
