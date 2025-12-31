#!/usr/bin/env node
/**
 * WebSocket Test Script for Express 5 + PostgreSQL + OpenTelemetry
 *
 * Tests WebSocket functionality including:
 * - Authentication
 * - Channel subscription
 * - Real-time article events
 *
 * Usage:
 *   node scripts/test-websocket.js
 *
 * Prerequisites:
 *   - Server running on PORT (default: 8000)
 *   - Registered user or will register a new one
 */

import { io } from 'socket.io-client';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8000';
const WS_URL = BASE_URL.replace(/^http/, 'ws');

let token = '';
let articleSlug = '';
let socket = null;
let pass = 0;
let fail = 0;

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const NC = '\x1b[0m';

function logPass(msg) {
  console.log(`${GREEN}✓ PASS${NC}: ${msg}`);
  pass++;
}

function logFail(msg) {
  console.log(`${RED}✗ FAIL${NC}: ${msg}`);
  fail++;
}

function logInfo(msg) {
  console.log(`${YELLOW}→${NC} ${msg}`);
}

async function apiRequest(method, path, body, authToken) {
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await response.json().catch(() => null);
  return { status: response.status, data };
}

async function setupUser() {
  logInfo('Setting up test user...');

  const email = `ws-test-${Date.now()}@example.com`;
  const { status, data } = await apiRequest('POST', '/api/register', {
    email,
    password: 'password123',
    name: 'WebSocket Test User',
  });

  if (status === 201 && data?.token) {
    token = data.token;
    logPass('User registered');
    return true;
  } else {
    logFail(`User registration failed: ${data?.error || 'Unknown error'}`);
    return false;
  }
}

function connectSocket() {
  return new Promise((resolve) => {
    logInfo('Connecting to WebSocket...');

    socket = io(BASE_URL, {
      auth: { token },
      transports: ['websocket'],
      reconnection: false,
    });

    socket.on('connect', () => {
      logPass(`Connected with socket ID: ${socket.id}`);
      resolve(true);
    });

    socket.on('connect_error', (err) => {
      logFail(`Connection failed: ${err.message}`);
      resolve(false);
    });

    setTimeout(() => {
      if (!socket.connected) {
        logFail('Connection timeout');
        resolve(false);
      }
    }, 5000);
  });
}

function subscribeToChannel(channel) {
  return new Promise((resolve) => {
    logInfo(`Subscribing to '${channel}' channel...`);

    const cleanup = () => {
      socket.off('subscribed', subscribedHandler);
      socket.off('error', errorHandler);
      clearTimeout(timer);
    };

    const subscribedHandler = (data) => {
      if (data.channel === channel) {
        cleanup();
        logPass(`Subscribed to '${channel}'`);
        resolve(true);
      }
    };

    const errorHandler = (data) => {
      if (data.message && data.message.includes(channel)) {
        cleanup();
        logFail(`Subscription error: ${data.message}`);
        resolve(false);
      }
    };

    socket.on('subscribed', subscribedHandler);
    socket.on('error', errorHandler);

    socket.emit('subscribe', channel);

    const timer = setTimeout(() => {
      cleanup();
      logFail('Subscription timeout');
      resolve(false);
    }, 5000);
  });
}

function waitForEvent(eventName, timeout = 10000) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      resolve({ success: false, error: 'timeout' });
    }, timeout);

    socket.once(eventName, (data) => {
      clearTimeout(timer);
      resolve({ success: true, data });
    });
  });
}

async function testArticleCreation() {
  logInfo('Testing article creation event...');

  const eventPromise = waitForEvent('article:created');

  const { status, data } = await apiRequest(
    'POST',
    '/api/articles',
    {
      title: 'WebSocket Test Article',
      description: 'Testing real-time updates',
      body: 'This article was created to test WebSocket functionality.',
    },
    token
  );

  if (status === 201 && data?.slug) {
    articleSlug = data.slug;
    logPass(`Article created via API: ${articleSlug}`);

    const event = await eventPromise;
    if (event.success) {
      logPass('Received article:created event');
      console.log('  Event data:', JSON.stringify(event.data, null, 2).slice(0, 200) + '...');
    } else {
      logFail('Did not receive article:created event (timeout)');
    }
  } else {
    logFail(`Article creation failed: ${data?.error || 'Unknown error'}`);
  }
}

async function testArticleUpdate() {
  if (!articleSlug) {
    logFail('No article to update');
    return;
  }

  logInfo('Testing article update event...');

  const eventPromise = waitForEvent('article:updated');

  const { status, data } = await apiRequest(
    'PUT',
    `/api/articles/${articleSlug}`,
    {
      title: 'Updated WebSocket Test Article',
      body: 'This article was updated to test WebSocket functionality.',
    },
    token
  );

  if (status === 200) {
    logPass('Article updated via API');

    const event = await eventPromise;
    if (event.success) {
      logPass('Received article:updated event');
    } else {
      logFail('Did not receive article:updated event (timeout)');
    }
  } else {
    logFail(`Article update failed: ${data?.error || 'Unknown error'}`);
  }
}

async function testArticleDeletion() {
  if (!articleSlug) {
    logFail('No article to delete');
    return;
  }

  logInfo('Testing article deletion event...');

  const eventPromise = waitForEvent('article:deleted');

  const { status } = await apiRequest('DELETE', `/api/articles/${articleSlug}`, null, token);

  if (status === 204) {
    logPass('Article deleted via API');

    const event = await eventPromise;
    if (event.success) {
      logPass('Received article:deleted event');
    } else {
      logFail('Did not receive article:deleted event (timeout)');
    }
  } else {
    logFail('Article deletion failed');
  }
}

async function testUnauthenticatedConnection() {
  logInfo('Testing unauthenticated connection (should fail)...');

  return new Promise((resolve) => {
    const unauthSocket = io(BASE_URL, {
      transports: ['websocket'],
      reconnection: false,
    });

    unauthSocket.on('connect', () => {
      logFail('Unauthenticated connection should have been rejected');
      unauthSocket.disconnect();
      resolve(false);
    });

    unauthSocket.on('connect_error', (err) => {
      if (err.message.includes('Authentication') || err.message.includes('required')) {
        logPass('Unauthenticated connection rejected as expected');
        resolve(true);
      } else {
        logPass(`Unauthenticated connection rejected: ${err.message}`);
        resolve(true);
      }
    });

    setTimeout(() => {
      unauthSocket.disconnect();
      logFail('Unauthenticated connection test timeout');
      resolve(false);
    }, 5000);
  });
}

async function testInvalidChannel() {
  logInfo('Testing invalid channel subscription...');

  return new Promise((resolve) => {
    const cleanup = () => {
      socket.off('error', errorHandler);
      socket.off('subscribed', subscribedHandler);
    };

    const errorHandler = (data) => {
      if (data.message && data.message.includes('Invalid channel')) {
        cleanup();
        logPass('Invalid channel subscription rejected');
        resolve(true);
      }
    };

    const subscribedHandler = () => {
      cleanup();
      logFail('Invalid channel subscription should have been rejected');
      resolve(false);
    };

    socket.on('error', errorHandler);
    socket.on('subscribed', subscribedHandler);

    socket.emit('subscribe', 'invalid-channel');

    setTimeout(() => {
      cleanup();
      logFail('Invalid channel test timeout');
      resolve(false);
    }, 5000);
  });
}

async function run() {
  console.log('========================================');
  console.log('Express 5 + PostgreSQL WebSocket Tests');
  console.log('========================================');
  console.log('');

  try {
    const userOk = await setupUser();
    if (!userOk) {
      throw new Error('Failed to set up user');
    }

    await testUnauthenticatedConnection();

    const connected = await connectSocket();
    if (!connected) {
      throw new Error('Failed to connect socket');
    }

    await subscribeToChannel('articles');
    await testInvalidChannel();
    await testArticleCreation();
    await testArticleUpdate();
    await testArticleDeletion();

    if (socket) {
      socket.disconnect();
      logPass('Socket disconnected cleanly');
    }
  } catch (err) {
    logFail(`Test error: ${err.message}`);
  }

  console.log('');
  console.log('========================================');
  console.log('Test Summary');
  console.log('========================================');
  console.log(`${GREEN}Passed: ${pass}${NC}`);
  console.log(`${RED}Failed: ${fail}${NC}`);
  console.log('');

  if (fail > 0) {
    console.log(`${RED}Some tests failed!${NC}`);
    process.exit(1);
  } else {
    console.log(`${GREEN}All tests passed!${NC}`);
    process.exit(0);
  }
}

run();
