package com.base14.demo.resource;

import com.base14.demo.dto.AuthDto.AuthResponse;
import com.base14.demo.dto.AuthDto.ErrorResponse;
import com.base14.demo.dto.AuthDto.LoginRequest;
import com.base14.demo.dto.AuthDto.MessageResponse;
import com.base14.demo.dto.AuthDto.RegisterRequest;
import com.base14.demo.dto.AuthDto.UserResponse;
import com.base14.demo.entity.User;
import com.base14.demo.service.AuthService;
import com.base14.demo.service.ServiceException;
import io.opentelemetry.api.trace.Span;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.core.SecurityContext;
import org.eclipse.microprofile.jwt.JsonWebToken;

@Path("/api")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class AuthResource {

    @Inject
    AuthService authService;

    @Inject
    JsonWebToken jwt;

    @POST
    @Path("/register")
    @PermitAll
    public Response register(RegisterRequest request) {
        if (request.email() == null || request.email().isBlank() ||
            request.password() == null || request.password().isBlank() ||
            request.name() == null || request.name().isBlank()) {
            return errorResponse(Response.Status.BAD_REQUEST, "email, password, and name are required");
        }

        try {
            AuthResponse response = authService.register(request);
            return Response.status(Response.Status.CREATED).entity(response).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @POST
    @Path("/login")
    @PermitAll
    public Response login(LoginRequest request) {
        if (request.email() == null || request.email().isBlank() ||
            request.password() == null || request.password().isBlank()) {
            return errorResponse(Response.Status.BAD_REQUEST, "email and password are required");
        }

        try {
            AuthResponse response = authService.login(request);
            return Response.ok(response).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @GET
    @Path("/user")
    @RolesAllowed("user")
    public Response getUser(@Context SecurityContext ctx) {
        try {
            Long userId = Long.parseLong(jwt.getSubject());
            User user = authService.getUser(userId);
            return Response.ok(UserResponse.from(user)).build();
        } catch (ServiceException e) {
            return errorResponse(Response.Status.fromStatusCode(e.getStatusCode()), e.getMessage());
        }
    }

    @POST
    @Path("/logout")
    @RolesAllowed("user")
    public Response logout() {
        return Response.ok(new MessageResponse("logged out successfully")).build();
    }

    private Response errorResponse(Response.Status status, String message) {
        String traceId = Span.current().getSpanContext().getTraceId();
        return Response.status(status)
                .entity(new ErrorResponse(message, traceId))
                .build();
    }
}
