const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');

const staticCanvas = document.createElement('canvas');
const staticCtx = staticCanvas.getContext('2d');

const dynamicCanvas = document.createElement('canvas');
const dynamicCtx = dynamicCanvas.getContext('2d');

let width = 800;
let height = 600;
let unitPixelSize = 40;

let objectCache = [];
let renderAllowed = false;

const socket = new WebSocket('ws://127.0.0.1:5555/ws');

socket.onopen = () => {
    console.log('Connected to WebSocket server.');
};

socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    handleWebSocketMessage(message);
};

socket.onclose = () => {
    console.log('Disconnected from WebSocket server.');
};

function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'screen_size':
            setScreenSize(message.width, message.height);
            break;
        case 'clear_screen':
            handleClearScreen();
            break;
        case 'draw_grid':
            drawGrid(message.unit_pixel_size);
            break;
        case 'draw_object':
            accumulateObject(message.coordinates, message.size, message.color, message.id, message.text);
            break;
        default:
            console.log('Unknown message type:', message.type);
    }
}

function setScreenSize(newWidth, newHeight) {
    canvas.width = newWidth;
    canvas.height = newHeight;
    staticCanvas.width = newWidth;
    staticCanvas.height = newHeight;
    dynamicCanvas.width = newWidth;
    dynamicCanvas.height = newHeight;

    width = newWidth;
    height = newHeight;

    clearScreenLayers();
    drawGrid(unitPixelSize);
}

function handleClearScreen() {
    clearDynamicLayer();
    renderCachedObjects();
    objectCache = [];
    renderAllowed = true;
}

function clearScreenLayers() {
    staticCtx.clearRect(0, 0, width, height);
    dynamicCtx.clearRect(0, 0, width, height);
    updateMainDisplay();
}

function clearDynamicLayer() {
    dynamicCtx.clearRect(0, 0, width, height);
    updateMainDisplay();
}

function drawGrid(unitSize) {
    unitPixelSize = unitSize;
    staticCtx.clearRect(0, 0, width, height);

    staticCtx.strokeStyle = 'white';
    staticCtx.lineWidth = 1;

    for (let i = 0; i < width; i += unitPixelSize) {
        staticCtx.beginPath();
        staticCtx.moveTo(i, 0);
        staticCtx.lineTo(i, height);
        staticCtx.stroke();
    }

    for (let j = 0; j < height; j += unitPixelSize) {
        staticCtx.beginPath();
        staticCtx.moveTo(0, j);
        staticCtx.lineTo(width, j);
        staticCtx.stroke();
    }

    updateMainDisplay();
}

function accumulateObject(coordinates, size, color, id, text) {
    objectCache.push({
        coordinates,
        size,
        color,
        id,
        text
    });

    if (renderAllowed) {
        drawObjectToDynamicLayer(coordinates, size, color, id, text);
    }
}

function drawObjectToDynamicLayer(coordinates, size, color, id, text) {
    const x = coordinates.x * unitPixelSize;
    const y = coordinates.y * unitPixelSize;
    const objWidth = size.x * unitPixelSize;
    const objHeight = size.y * unitPixelSize;

    dynamicCtx.fillStyle = `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${color[3]})`;
    dynamicCtx.fillRect(x, y, objWidth, objHeight);

    if (text || text == "0") {
        drawText(dynamicCtx, text, x + objWidth / 2, y + objHeight / 2);
    }
}

function drawText(context, text, x, y) {
    context.save();

    context.fillStyle = 'white';
    context.font = '16px Arial';
    context.textAlign = 'center';
    context.textBaseline = 'middle';

    context.globalAlpha = 1.0;

    context.fillText(text, x, y);

    context.restore();
}

function renderCachedObjects() {
    objectCache.forEach(({
        coordinates,
        size,
        color,
        id,
        text
    }) => {
        drawObjectToDynamicLayer(coordinates, size, color, id, text);
    });

    updateMainDisplay();
}

function updateMainDisplay() {
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(staticCanvas, 0, 0);
    ctx.drawImage(dynamicCanvas, 0, 0);
}
