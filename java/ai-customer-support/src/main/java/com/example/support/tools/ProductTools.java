package com.example.support.tools;

import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductTools {

    private static final Logger log = LoggerFactory.getLogger(ProductTools.class);

    private final JdbcTemplate jdbc;

    public ProductTools(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Tool(description = "Search product catalog by name, description, or category")
    public List<Map<String, Object>> searchProducts(
        @ToolParam(description = "Search query (product name or keywords)") String query,
        @ToolParam(description = "Category filter (optional, empty string for all)") String category
    ) {
        log.info("Tool call: searchProducts(query={}, category={})", query, category);

        if (category != null && !category.isBlank()) {
            return jdbc.queryForList(
                """
                SELECT name, description, category, price, sku, in_stock
                FROM products
                WHERE category = ? AND (LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?))
                LIMIT 10
                """, category, "%" + query + "%", "%" + query + "%");
        }

        return jdbc.queryForList(
            """
            SELECT name, description, category, price, sku, in_stock
            FROM products
            WHERE LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?)
            LIMIT 10
            """, "%" + query + "%", "%" + query + "%");
    }

    @Tool(description = "Get detailed product information by SKU")
    public Map<String, Object> getProductInfo(
        @ToolParam(description = "Product SKU") String sku
    ) {
        log.info("Tool call: getProductInfo({})", sku);
        var rows = jdbc.queryForList(
            "SELECT name, description, category, price, sku, in_stock FROM products WHERE sku = ?", sku);

        if (rows.isEmpty()) {
            return Map.of("error", "Product not found: " + sku);
        }
        return rows.getFirst();
    }
}
