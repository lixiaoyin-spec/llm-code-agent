const { SnakeGame } = require('./game.js');

// 固定随机种子用于测试
function createTestGame(seed = 42) {
    const random = () => {
        seed = (seed * 9301 + 49297) % 233280;
        return seed / 233280;
    };
    return new SnakeGame(20, 20, random);
}

// 测试初始状态
const assert = require('node:assert');
const test = require('node:test');

test('初始状态', () => {
    const game = createTestGame();
    assert.deepStrictEqual(game.snake, [[10, 10], [9, 10], [8, 10]]);
    assert.strictEqual(game.direction, 'right');
    assert.strictEqual(game.score, 0);
    assert.strictEqual(game.gameOver, false);
    assert.strictEqual(game.getBoard().length, 20);
    assert.strictEqual(game.getBoard()[0].length, 20);
});

test('向右移动', () => {
    const game = createTestGame();
    const result = game.step('right');
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, false);
    assert.deepStrictEqual(game.snake, [[11, 10], [10, 10], [9, 10]]);
});

test('向左移动', () => {
    const game = createTestGame();
    // 先改变方向为向下，然后向左移动（不是180度掉头）
    game.step('down');  // 先向下移动
    const result = game.step('left');  // 向左移动
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, false);
    assert.deepStrictEqual(game.snake, [[10, 11], [10, 10], [9, 10]]);  // 向左移动
});

test('向上移动', () => {
    const game = createTestGame();
    const result = game.step('up');
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, false);
    assert.deepStrictEqual(game.snake, [[10, 9], [10, 10], [9, 10]]);
});

test('向下移动', () => {
    const game = createTestGame();
    const result = game.step('down');
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, false);
    assert.deepStrictEqual(game.snake, [[10, 11], [10, 10], [9, 10]]);
});

test('180度掉头被忽略', () => {
    const game = createTestGame();
    game.step('right');  // 先向右
    const result = game.step('left');  // 尝试向左（180度掉头）
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, false);
    assert.strictEqual(game.direction, 'right');
    assert.deepStrictEqual(game.snake[0], [12, 10]);  // 继续向右
});

test('吃食物', () => {
    const game = createTestGame();
    // 设置食物在蛇头前方
    game.food = [11, 10];
    const result = game.step('right');
    assert.strictEqual(result.ateFood, true);
    assert.strictEqual(result.gameOver, false);
    assert.strictEqual(game.score, 1);
    assert.strictEqual(game.snake.length, 4);  // 蛇增长
});

test('撞墙', () => {
    const game = createTestGame();
    // 移动到右墙边
    for (let i = 0; i < 8; i++) {
        game.step('right');
    }
    const result = game.step('right');  // 撞墙
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, true);
    assert.strictEqual(game.gameOver, true);
});

test('撞自己', () => {
    const game = createTestGame();
    // 创建一个U形让蛇撞到自己
    game.snake = [[5, 5], [6, 5], [7, 5], [7, 6], [7, 7], [6, 7], [5, 7]];
    game.direction = 'left';
    // 设置食物在[4,5]，这样蛇会向左移动到[4,5]然后撞到自己
    game.food = [4, 5];
    const result = game.step('left');  // 向左移动会撞到自己
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, true);
    assert.strictEqual(game.gameOver, true);
});

test('食物不会生成在蛇身上', () => {
    const game = createTestGame();
    // 生成多次食物，确保都不在蛇身上
    for (let i = 0; i < 100; i++) {
        const food = game._generateFood();
        assert.strictEqual(game.snake.some(segment => 
            segment[0] === food[0] && segment[1] === food[1]), false);
    }
});

test('游戏结束后不能再移动', () => {
    const game = createTestGame();
    // 撞墙
    for (let i = 0; i < 8; i++) {
        game.step('right');
    }
    game.step('right');  // 撞墙，游戏结束
    assert.strictEqual(game.gameOver, true);
    
    // 游戏结束后不能再移动
    const result = game.step('right');
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, true);
});

test('暂停功能', () => {
    const game = createTestGame();
    game.togglePause();
    assert.strictEqual(game.paused, true);
    
    const result = game.step('right');
    assert.strictEqual(result.ateFood, false);
    assert.strictEqual(result.gameOver, false);
    assert.deepStrictEqual(game.snake, [[10, 10], [9, 10], [8, 10]]);  // 没有移动
    
    game.togglePause();
    assert.strictEqual(game.paused, false);
    
    const result2 = game.step('right');
    assert.strictEqual(result2.ateFood, false);
    assert.strictEqual(result2.gameOver, false);
    assert.deepStrictEqual(game.snake, [[11, 10], [10, 10], [9, 10]]);  // 移动了
});

test('重置功能', () => {
    const game = createTestGame();
    game.step('right');
    game.score = 5;
    game.gameOver = true;
    
    game.reset();
    assert.deepStrictEqual(game.snake, [[10, 10], [9, 10], [8, 10]]);
    assert.strictEqual(game.direction, 'right');
    assert.strictEqual(game.score, 0);
    assert.strictEqual(game.gameOver, false);
    assert.strictEqual(game.paused, false);
});

test('棋盘渲染', () => {
    const game = createTestGame();
    const board = game.getBoard();
    
    // 检查墙
    assert.strictEqual(board[0][0], '#');
    assert.strictEqual(board[0][19], '#');
    assert.strictEqual(board[19][0], '#');
    assert.strictEqual(board[19][19], '#');
    
    // 检查蛇头
    assert.strictEqual(board[10][10], 'O');
    
    // 检查蛇身
    assert.strictEqual(board[10][9], 'o');
    assert.strictEqual(board[10][8], 'o');
    
    // 检查食物
    assert.strictEqual(board[10][10], 'O');  // 蛇头位置
});