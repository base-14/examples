import { UserResponseDto } from '../../users/dto/user-response.dto';

export class AuthResponseDto {
  user: UserResponseDto;
  token: string;
  expiresIn: string;
  expiresAt: number;
  tokenType: string;
}
