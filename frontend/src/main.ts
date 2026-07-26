import { createApp } from 'vue'
import { createThemeProvider } from '@quantumaudio/ableton-extension-sdk'
import '@quantumaudio/ableton-extension-sdk/theme.css'
import '@quantumaudio/ableton-extension-sdk/styles.css'
import './styles/tokens.css'
import 'splitpanes/dist/splitpanes.css'
import './styles/dock.css'
import App from './App.vue'

createThemeProvider(document.documentElement, { defaultTheme: 'dark' })
document.documentElement.setAttribute('data-qa-theme', 'dark')

createApp(App).mount('#app')
