import NextAuth from 'next-auth'

const { handlers } = NextAuth({ providers: [] })
export const { GET, POST } = handlers
