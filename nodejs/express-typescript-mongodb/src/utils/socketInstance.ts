import type { Server } from 'socket.io';

let io: Server | null = null;

export function setSocketIO(socketIO: Server): void {
  io = socketIO;
}

export function getSocketIO(): Server | null {
  return io;
}
