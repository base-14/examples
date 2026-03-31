import { router, publicProcedure } from "../router";
import { PrismaClient } from "@prisma/client";

export function createHealthRouter(prisma: PrismaClient) {
  return router({
    check: publicProcedure.query(async () => {
      await prisma.$queryRaw`SELECT 1`;
      return {
        status: "healthy",
        service: "trpc-articles",
        timestamp: new Date().toISOString(),
      };
    }),
  });
}
