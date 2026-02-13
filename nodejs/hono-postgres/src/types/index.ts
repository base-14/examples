export interface JwtPayload {
  id: number;
  email: string;
}

export type Variables = {
  user: JwtPayload;
};
