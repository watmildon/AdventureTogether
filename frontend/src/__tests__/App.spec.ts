import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'
import AppHeader from '../components/AppHeader.vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import appRouter from '../router'

const stub = { template: '<div>Stub</div>' }
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div>Home View Stub</div>' } },
    { path: '/backoffice', component: stub },
    { path: '/backoffice/events/:id', component: stub }
  ]
})

describe('App Root Component', () => {
  it('renders the header and main content wrapper', async () => {
    router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router]
      }
    })

    expect(wrapper.findComponent(AppHeader).exists()).toBe(true)
    expect(wrapper.find('.main-content').exists()).toBe(true)
  })
})

describe('AppHeader', () => {
  it('shows the participant header with a small Back office link', async () => {
    await router.push('/')
    const wrapper = mount(AppHeader, { global: { plugins: [router] } })
    expect(wrapper.find('.app-header').classes()).not.toContain('backoffice')
    expect(wrapper.find('.nav-item-small').attributes('href')).toBe('/backoffice')
    expect(wrapper.text()).not.toContain('Participants')
  })

  it('shows the back-office title and a link back to participants on back-office routes', async () => {
    await router.push('/backoffice/events/2')
    const wrapper = mount(AppHeader, { global: { plugins: [router] } })
    expect(wrapper.find('.app-header').classes()).toContain('backoffice')
    expect(wrapper.find('.area-title').text()).toBe('Back office')
    const participants = wrapper.findAll('.nav-item').find((a) => a.text() === 'Participants')
    expect(participants?.attributes('href')).toBe('/')
  })
})

describe('app router', () => {
  it('redirects the old host URLs to the back office', () => {
    // resolve() follows no redirects, so read the redirect function off the matched record
    const builder = appRouter.resolve('/events/2/host/builder')
    const verify = appRouter.resolve('/events/2/host/verify')
    const follow = (resolved: typeof builder) => {
      const redirect = resolved.matched[0].redirect as (to: any) => { path: string }
      return redirect(resolved).path
    }
    expect(follow(builder)).toBe('/backoffice/events/2/quests')
    expect(follow(verify)).toBe('/backoffice/events/2/verify')
  })

  it('keeps the participant routes and nests the manage tabs under the event', () => {
    expect(appRouter.resolve('/events/2/map').name).toBe('event-map')
    expect(appRouter.resolve('/events/2/join').name).toBe('join-team')
    expect(appRouter.resolve('/backoffice').name).toBe('backoffice')
    expect(appRouter.resolve('/backoffice/events/new').name).toBe('backoffice-event-new')
    expect(appRouter.resolve('/backoffice/events/2/edit').name).toBe('backoffice-event-edit')
    expect(appRouter.resolve('/backoffice/events/2').name).toBe('backoffice-event')
    expect(appRouter.resolve('/backoffice/events/2/quests').name).toBe('backoffice-quests')
    expect(appRouter.resolve('/backoffice/events/2/verify').name).toBe('backoffice-verify')
    expect(appRouter.resolve('/backoffice/events/2/teams').name).toBe('backoffice-teams')
  })
})
