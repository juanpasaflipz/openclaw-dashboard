import nextra from 'nextra'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

const withNextra = nextra({})

export default withNextra({
  reactStrictMode: true,
  outputFileTracingRoot: join(__dirname, '.')
})
