package com.base14.demo.resource;

import jakarta.annotation.security.PermitAll;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import java.util.Map;

@Path("/api/health")
@Produces(MediaType.APPLICATION_JSON)
public class HealthResource {

    @Inject
    EntityManager em;

    @GET
    @PermitAll
    public Response health() {
        String dbStatus = "connected";
        try {
            em.createNativeQuery("SELECT 1").getSingleResult();
        } catch (Exception e) {
            dbStatus = "disconnected";
            return Response.status(Response.Status.SERVICE_UNAVAILABLE)
                    .entity(Map.of("status", "unhealthy", "database", dbStatus))
                    .build();
        }

        return Response.ok(Map.of("status", "healthy", "database", dbStatus)).build();
    }
}
