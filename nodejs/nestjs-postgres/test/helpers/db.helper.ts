import { DataSource } from 'typeorm';
import { INestApplication } from '@nestjs/common';

export async function clearDatabase(app: INestApplication): Promise<void> {
  const dataSource = app.get(DataSource);

  const entities = dataSource.entityMetadatas;

  for (const entity of entities) {
    const repository = dataSource.getRepository(entity.name);
    await repository.query(
      `TRUNCATE TABLE "${entity.tableName}" RESTART IDENTITY CASCADE`,
    );
  }
}

export async function seedDatabase(
  app: INestApplication,
  seeds: Record<string, unknown[]>,
): Promise<void> {
  const dataSource = app.get(DataSource);

  for (const [entityName, data] of Object.entries(seeds)) {
    const repository = dataSource.getRepository(entityName);
    await repository.save(data);
  }
}
