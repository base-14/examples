package com.example.support.config;

import javax.sql.DataSource;

import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.pgvector.PgVectorStore;
import org.springframework.ai.vectorstore.pgvector.PgVectorStore.PgDistanceType;
import org.springframework.ai.vectorstore.pgvector.PgVectorStore.PgIndexType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class VectorStoreConfig {

    @Bean
    PgVectorStore vectorStore(EmbeddingModel embeddingModel, DataSource dataSource) {
        return PgVectorStore.builder(new JdbcTemplate(dataSource), embeddingModel)
            .dimensions(1536)
            .distanceType(PgDistanceType.COSINE_DISTANCE)
            .indexType(PgIndexType.HNSW)
            .initializeSchema(false)
            .build();
    }
}
