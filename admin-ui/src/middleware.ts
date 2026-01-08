import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Paths that don't require authentication
const publicPaths = ['/login', '/register'];

// Paths that should be checked for auth (protected)
const protectedPaths = ['/', '/chat', '/prompts', '/tools', '/templates', '/instances', '/sessions', '/profile'];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  
  // Skip static files and API routes
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname.includes('.')
  ) {
    return NextResponse.next();
  }

  // Check if current path is public
  const isPublicPath = publicPaths.some(path => pathname === path || pathname.startsWith(path + '/'));
  
  // Check if current path is protected
  const isProtectedPath = protectedPaths.some(path => pathname === path || pathname.startsWith(path + '/'));

  // Get session token from cookie
  const sessionToken = request.cookies.get('session_token')?.value;

  // If accessing protected path without session token, redirect to login
  if (isProtectedPath && !sessionToken) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('from', pathname);
    return NextResponse.redirect(loginUrl);
  }

  // If accessing public path with session token, redirect to chat
  if (isPublicPath && sessionToken) {
    return NextResponse.redirect(new URL('/chat', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
