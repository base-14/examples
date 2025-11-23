<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\LoginRequest;
use App\Http\Requests\RegisterRequest;
use App\Http\Resources\UserResource;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Hash;
use Tymon\JWTAuth\Facades\JWTAuth;

class AuthController extends Controller
{
    public function register(RegisterRequest $request): JsonResponse
    {
        $user = User::create([
            'name' => $request->name,
            'email' => $request->email,
            'password' => Hash::make($request->password),
        ]);

        $token = JWTAuth::fromUser($user);
        $user->token = $token;

        return response()->json([
            'user' => new UserResource($user),
        ], 201);
    }

    public function login(LoginRequest $request): JsonResponse
    {
        $credentials = $request->only('email', 'password');

        if (! $token = auth('api')->attempt($credentials)) {
            return response()->json(['error' => 'Invalid credentials'], 401);
        }

        $user = auth('api')->user();
        $user->token = $token;

        return response()->json([
            'user' => new UserResource($user),
        ]);
    }

    public function logout(): JsonResponse
    {
        auth('api')->logout();

        return response()->json(['message' => 'Successfully logged out']);
    }

    public function me(): JsonResponse
    {
        return response()->json([
            'user' => new UserResource(auth('api')->user()),
        ]);
    }

    public function refresh(): JsonResponse
    {
        $token = auth('api')->refresh();
        $user = auth('api')->user();
        $user->token = $token;

        return response()->json([
            'user' => new UserResource($user),
        ]);
    }
}
