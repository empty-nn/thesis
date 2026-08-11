export interface AuthUser {
  id: string;
  email?: string;
  displayName?: string;
  profilePictureUrl?: string;
}

export interface GoogleLoginResponse {
  user: AuthUser;
  isNewUser: boolean;
  authenticatedAt: string;
}
