import { MongoMemoryServer } from 'mongodb-memory-server';
import mongoose from 'mongoose';

let mongoServer: MongoMemoryServer | null = null;

export async function setupTestDatabase(): Promise<void> {
  if (mongoServer) {
    throw new Error('MongoDB test server already running');
  }

  mongoServer = await MongoMemoryServer.create({
    binary: {
      version: '8.0.0',
    },
    instance: {
      dbName: 'test-db',
    },
  });

  const mongoUri = mongoServer.getUri();

  await mongoose.connect(mongoUri, {
    serverSelectionTimeoutMS: 5000,
  });
}

export async function teardownTestDatabase(): Promise<void> {
  if (mongoose.connection.readyState !== 0) {
    await mongoose.connection.dropDatabase();
    await mongoose.connection.close();
  }

  if (mongoServer) {
    await mongoServer.stop();
    mongoServer = null;
  }
}

export async function clearDatabase(): Promise<void> {
  if (mongoose.connection.readyState === 0) {
    throw new Error('Database not connected');
  }

  const collections = mongoose.connection.collections;

  await Promise.all(
    Object.values(collections).map((collection) => collection.deleteMany({}))
  );
}

export async function seedDatabase<T>(
  model: mongoose.Model<T>,
  data: Partial<T>[]
): Promise<(mongoose.Document<unknown, object, T> & T)[]> {
  return model.insertMany(data);
}
