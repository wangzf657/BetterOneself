import { createBrowserRouter } from 'react-router-dom'
import { RootLayout } from './layout'
import { StudyLayout } from './study-layout'
import { TodayPage } from '@/features/today/page'
import { StudiesPage } from '@/features/studies/page'
import { SourcesPage } from '@/features/sources/manage'
import { SourceReadPage } from '@/features/sources/read'
import { KnowledgePage } from '@/features/knowledge/page'
import { LearnPage } from '@/features/learn/session'
import { ReviewPage } from '@/features/review/page'
import { InterviewPage } from '@/features/plan/interview'
import { PlanPage } from '@/features/plan/page'

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/', element: <TodayPage /> },
      { path: '/studies', element: <StudiesPage /> },
      { path: '/review', element: <ReviewPage /> },
      {
        path: '/studies/:id',
        element: <StudyLayout />,
        children: [
          { path: 'sources', element: <SourcesPage /> },
          { path: 'sources/:sid', element: <SourceReadPage /> },
          { path: 'knowledge', element: <KnowledgePage /> },
          { path: 'plan', element: <PlanPage /> },
          { path: 'plan/interview', element: <InterviewPage /> },
          { path: 'learn/:sessionId', element: <LearnPage /> },
        ],
      },
    ],
  },
])
