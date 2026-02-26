package com.example.support.tools;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import com.example.support.telemetry.SupportMetrics;

@Component
public class OrderTools {

    private static final Logger log = LoggerFactory.getLogger(OrderTools.class);

    private final JdbcTemplate jdbc;
    private final SupportMetrics metrics;

    public OrderTools(JdbcTemplate jdbc, SupportMetrics metrics) {
        this.jdbc = jdbc;
        this.metrics = metrics;
    }

    @Tool(description = "Look up order status and tracking info by order ID (e.g. ORD-12345)")
    public Map<String, Object> getOrderStatus(
        @ToolParam(description = "Order ID, e.g. ORD-12345") String orderId
    ) {
        log.info("Tool call: getOrderStatus({})", orderId);
        metrics.recordToolCall("getOrderStatus", true);
        var rows = jdbc.queryForList(
            """
            SELECT o.order_id, o.status, o.tracking_number, o.estimated_delivery,
                   o.total_amount, o.created_at, c.name as customer_name
            FROM orders o JOIN customers c ON o.customer_id = c.id
            WHERE o.order_id = ?
            """, orderId);

        if (rows.isEmpty()) {
            return Map.of("error", "Order not found: " + orderId);
        }
        return rows.getFirst();
    }

    @Tool(description = "Get a customer's recent orders by customer email address")
    public List<Map<String, Object>> getOrderHistory(
        @ToolParam(description = "Customer email address") String email,
        @ToolParam(description = "Maximum number of orders to return") int limit
    ) {
        log.info("Tool call: getOrderHistory(email={}, limit={})", email, limit);
        metrics.recordToolCall("getOrderHistory", true);
        return jdbc.queryForList(
            """
            SELECT o.order_id, o.status, o.total_amount, o.created_at
            FROM orders o JOIN customers c ON o.customer_id = c.id
            WHERE c.email = ?
            ORDER BY o.created_at DESC LIMIT ?
            """, email, Math.min(limit, 10));
    }

    @Tool(description = "Initiate a return for an order. Returns must be within 30 days of delivery.")
    public Map<String, Object> initiateReturn(
        @ToolParam(description = "Order ID to return, e.g. ORD-12345") String orderId,
        @ToolParam(description = "Reason for the return") String reason
    ) {
        log.info("Tool call: initiateReturn(orderId={}, reason={})", orderId, reason);
        metrics.recordToolCall("initiateReturn", true);

        var orders = jdbc.queryForList(
            "SELECT id, status, total_amount FROM orders WHERE order_id = ?", orderId);
        if (orders.isEmpty()) {
            return Map.of("error", "Order not found: " + orderId);
        }

        var order = orders.getFirst();
        String status = (String) order.get("status");
        if (!"delivered".equals(status)) {
            return Map.of("error", "Returns can only be initiated for delivered orders. Current status: " + status);
        }

        UUID orderUuid = (UUID) order.get("id");
        String returnId = "RET-" + (10000 + (int) (Math.random() * 90000));

        jdbc.update(
            "INSERT INTO returns (order_id, return_id, reason, status, refund_amount) VALUES (?, ?, ?, 'pending', ?)",
            orderUuid, returnId, reason, order.get("total_amount"));

        return Map.of(
            "return_id", returnId,
            "order_id", orderId,
            "status", "pending",
            "refund_amount", order.get("total_amount"),
            "message", "Return initiated. A prepaid shipping label will be emailed to you."
        );
    }

    @Tool(description = "Check the status of a return by return ID (e.g. RET-67890)")
    public Map<String, Object> getReturnStatus(
        @ToolParam(description = "Return ID, e.g. RET-67890") String returnId
    ) {
        log.info("Tool call: getReturnStatus({})", returnId);
        metrics.recordToolCall("getReturnStatus", true);
        var rows = jdbc.queryForList(
            """
            SELECT r.return_id, r.reason, r.status, r.refund_amount, r.created_at,
                   o.order_id
            FROM returns r JOIN orders o ON r.order_id = o.id
            WHERE r.return_id = ?
            """, returnId);

        if (rows.isEmpty()) {
            return Map.of("error", "Return not found: " + returnId);
        }
        return rows.getFirst();
    }
}
