class SnakeGame {
    constructor(width = 20, height = 20, randomSource = null) {
        this.width = width;
        this.height = height;
        this.random = randomSource || Math.random;
        
        // 初始化蛇：头部在中间，向右延伸
        this.snake = [[10, 10], [9, 10], [8, 10]];
        this.direction = 'right';
        this.score = 0;
        this.gameOver = false;
        this.paused = false;
        
        // 生成第一个食物
        this.food = this._generateFood();
    }
    
    _generateFood() {
        /* 生成不在蛇身上的食物 */
        while (true) {
            const x = Math.floor(this.random() * (this.width - 2)) + 1;
            const y = Math.floor(this.random() * (this.height - 2)) + 1;
            if (!this.snake.some(segment => segment[0] === x && segment[1] === y)) {
                return [x, y];
            }
        }
    }
    
    step(direction) {
        /* 执行一步移动，返回 { ateFood, gameOver } */
        if (this.gameOver || this.paused) {
            return { ateFood: false, gameOver: this.gameOver };
        }
        
        // 检查180度掉头
        const opposite = {
            'right': 'left', 'left': 'right',
            'up': 'down', 'down': 'up'
        };
        if (direction in opposite && direction === opposite[this.direction]) {
            // 忽略180度掉头，保持原方向，继续移动
            direction = this.direction;
        }
        
        // 计算新头部位置
        const head = this.snake[0];
        let newHead;
        switch (direction) {
            case 'right':
                newHead = [head[0] + 1, head[1]];
                break;
            case 'left':
                newHead = [head[0] - 1, head[1]];
                break;
            case 'down':
                newHead = [head[0], head[1] + 1];
                break;
            case 'up':
                newHead = [head[0], head[1] - 1];
                break;
            default:
                return { ateFood: false, gameOver: false };
        }
        
        // 检查撞墙
        if (newHead[0] < 1 || newHead[0] >= this.width - 1 ||
            newHead[1] < 1 || newHead[1] >= this.height - 1) {
            this.gameOver = true;
            return { ateFood: false, gameOver: true };
        }
        
        // 检查撞自己（排除蛇尾）
        if (this.snake.slice(0, -1).some(segment => 
            segment[0] === newHead[0] && segment[1] === newHead[1])) {
            this.gameOver = true;
            return { ateFood: false, gameOver: true };
        }
        
        // 移动蛇
        this.snake.unshift(newHead);
        
        // 检查是否吃到食物
        if (newHead[0] === this.food[0] && newHead[1] === this.food[1]) {
            this.score += 1;
            this.food = this._generateFood();
            return { ateFood: true, gameOver: false };
        } else {
            this.snake.pop();
            return { ateFood: false, gameOver: false };
        }
    }
    
    getBoard() {
        /* 获取当前棋盘二维数组 */
        const board = Array(this.height).fill().map(() => Array(this.width).fill(' '));
        
        // 画墙
        for (let x = 0; x < this.width; x++) {
            board[0][x] = '#';
            board[this.height - 1][x] = '#';
        }
        for (let y = 0; y < this.height; y++) {
            board[y][0] = '#';
            board[y][this.width - 1] = '#';
        }
        
        // 画蛇
        this.snake.forEach((segment, index) => {
            if (index === 0) {
                board[segment[1]][segment[0]] = 'O'; // 蛇头
            } else {
                board[segment[1]][segment[0]] = 'o'; // 蛇身
            }
        });
        
        // 画食物
        board[this.food[1]][this.food[0]] = '*';
        
        return board;
    }
    
    reset() {
        /* 重置游戏 */
        this.snake = [[10, 10], [9, 10], [8, 10]];
        this.direction = 'right';
        this.score = 0;
        this.gameOver = false;
        this.paused = false;
        this.food = this._generateFood();
    }
    
    togglePause() {
        /* 切换暂停状态 */
        this.paused = !this.paused;
    }
}

// CommonJS 导出
if (typeof module !== "undefined") {
    module.exports = { SnakeGame };
}