const io = require('socket.io-client');

const SERVER_URL = process.env.SERVER_URL || 'http://localhost:3000';
const JWT_TOKEN = process.env.JWT_TOKEN || '';

if (!JWT_TOKEN) {
  console.error('Please provide a JWT token via JWT_TOKEN environment variable');
  console.error('Example: JWT_TOKEN=your_token_here node websocket-client.js');
  process.exit(1);
}

const socket = io(SERVER_URL, {
  auth: {
    token: JWT_TOKEN,
  },
});

socket.on('connect', () => {
  console.log('✓ Connected to WebSocket server');
  console.log(`Socket ID: ${socket.id}`);

  socket.emit('subscribe:articles');
});

socket.on('connected', (data) => {
  console.log('✓ Server acknowledged connection');
  console.log(`User ID: ${data.userId}`);
  console.log(`Message: ${data.message}`);
});

socket.on('subscribed', (data) => {
  console.log(`✓ Subscribed to channel: ${data.channel}`);
  console.log('Listening for article updates...\n');
});

socket.on('unsubscribed', (data) => {
  console.log(`✓ Unsubscribed from channel: ${data.channel}`);
});

socket.on('disconnect', (reason) => {
  console.log(`✗ Disconnected: ${reason}`);
});

socket.on('connect_error', (error) => {
  console.error('✗ Connection error:', error.message);
  process.exit(1);
});

socket.on('article:created', (data) => {
  console.log('\n📝 ARTICLE CREATED');
  console.log(`   ID: ${data.id}`);
  console.log(`   Title: ${data.title}`);
  console.log(`   Author: ${data.authorId}`);
  console.log(`   Published: ${data.published}`);
  console.log(`   Timestamp: ${new Date(data.timestamp).toLocaleString()}`);
});

socket.on('article:updated', (data) => {
  console.log('\n✏️  ARTICLE UPDATED');
  console.log(`   ID: ${data.id}`);
  console.log(`   Title: ${data.title}`);
  console.log(`   Author: ${data.authorId}`);
  console.log(`   Published: ${data.published}`);
  console.log(`   Timestamp: ${new Date(data.timestamp).toLocaleString()}`);
});

socket.on('article:deleted', (data) => {
  console.log('\n🗑️  ARTICLE DELETED');
  console.log(`   ID: ${data.id}`);
  console.log(`   Title: ${data.title}`);
  console.log(`   Author: ${data.authorId}`);
  console.log(`   Timestamp: ${new Date(data.timestamp).toLocaleString()}`);
});

socket.on('article:published', (data) => {
  console.log('\n🚀 ARTICLE PUBLISHED');
  console.log(`   ID: ${data.id}`);
  console.log(`   Title: ${data.title}`);
  console.log(`   Author: ${data.authorId}`);
  console.log(`   Published: ${data.published}`);
  console.log(`   Timestamp: ${new Date(data.timestamp).toLocaleString()}`);
});

process.on('SIGINT', () => {
  console.log('\nDisconnecting...');
  socket.disconnect();
  process.exit(0);
});

console.log(`Connecting to ${SERVER_URL}...`);
