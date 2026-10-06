/**
 * AdventureTogether Vue Router Configuration
 *
 * Two surfaces:
 *   - Participants: the landing page (`/`), an event's map and its join/create-team page.
 *   - Back office (`/backoffice/...`) for hosts: events list, event form, and a manage page
 *     per event whose tabs are the overview, quest builder, verification and teams.
 *     No auth yet; the back office is simply linked from the header.
 *
 * Back-office views are lazy-loaded to keep the participants' mobile bundle small.
 */

import { createRouter, createWebHistory, type RouteLocationGeneric } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import EventMapView from '../views/EventMapView.vue'
import JoinTeamView from '../views/JoinTeamView.vue'

/** Redirect target builder for the pre-back-office host URLs, which hosts may have bookmarked. */
const toBackoffice = (tab: string) => (to: RouteLocationGeneric) => ({
  path: `/backoffice/events/${to.params.id}/${tab}`
})

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // Participants
    { path: '/', name: 'home', component: HomeView },
    { path: '/events/:id/map', name: 'event-map', component: EventMapView },
    { path: '/events/:id/join', name: 'join-team', component: JoinTeamView },

    // Old host URLs
    { path: '/events/:id/host/builder', redirect: toBackoffice('quests') },
    { path: '/events/:id/host/verify', redirect: toBackoffice('verify') },

    // Back office
    {
      path: '/backoffice',
      name: 'backoffice',
      component: () => import('../views/backoffice/BackofficeEventsView.vue')
    },
    {
      path: '/backoffice/events/new',
      name: 'backoffice-event-new',
      component: () => import('../views/backoffice/EventFormView.vue')
    },
    {
      path: '/backoffice/events/:id/edit',
      name: 'backoffice-event-edit',
      component: () => import('../views/backoffice/EventFormView.vue')
    },
    {
      path: '/backoffice/events/:id',
      component: () => import('../views/backoffice/ManageEventView.vue'),
      children: [
        {
          path: '',
          name: 'backoffice-event',
          component: () => import('../views/backoffice/EventOverviewView.vue')
        },
        {
          path: 'quests',
          name: 'backoffice-quests',
          component: () => import('../views/HostQuestBuilderView.vue')
        },
        {
          path: 'verify',
          name: 'backoffice-verify',
          component: () => import('../views/HostVerificationView.vue')
        },
        {
          path: 'teams',
          name: 'backoffice-teams',
          component: () => import('../views/backoffice/EventTeamsView.vue')
        }
      ]
    }
  ]
})

export default router
