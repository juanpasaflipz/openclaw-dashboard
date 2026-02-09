import { Footer, Layout, Navbar } from 'nextra-theme-docs'
import { Head } from 'nextra/components'
import { getPageMap } from 'nextra/page-map'
import type { ReactNode } from 'react'
import type { Metadata } from 'next'
import 'nextra-theme-docs/style.css'

export const metadata: Metadata = {
  title: {
    default: 'Green Monkey Docs',
    template: '%s - Green Monkey Docs'
  },
  description:
    'Documentation for Green Monkey Dashboard — configure your personalized AI agent with a modern web interface.'
}

const navbar = (
  <Navbar
    logo={
      <span style={{ fontWeight: 800, fontSize: '1.1rem' }}>
        🐵 Green Monkey Docs
      </span>
    }
    projectLink="https://github.com/juanpasaflipz/openclaw-dashboard"
  />
)

const footer = (
  <Footer>
    <span>MIT {new Date().getFullYear()} © Green Monkey</span>
  </Footer>
)

export default async function RootLayout({
  children
}: {
  children: ReactNode
}) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          navbar={navbar}
          pageMap={await getPageMap()}
          docsRepositoryBase="https://github.com/juanpasaflipz/openclaw-dashboard/tree/main/docs"
          footer={footer}
          editLink="Edit this page on GitHub"
          sidebar={{ defaultMenuCollapseLevel: 1 }}
        >
          {children}
        </Layout>
      </body>
    </html>
  )
}
