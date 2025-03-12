-- OpenManus 任务管理系统数据库表结构
-- 创建日期: 2023-11-25
-- 描述: 本文件包含任务管理系统所需的数据库表结构，适用于MySQL数据库

-- 创建任务表
CREATE TABLE IF NOT EXISTS tasks (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '任务ID，主键',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    prompt VARCHAR(2000) NOT NULL COMMENT '提示词内容',
    status VARCHAR(20) NOT NULL COMMENT '任务状态: pending, running, completed, failed',
    log_url VARCHAR(512) COMMENT '日志文件COS存储URL',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务记录表';

-- 创建文件表
CREATE TABLE IF NOT EXISTS files (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '文件ID，主键',
    task_id INT NOT NULL COMMENT '关联的任务ID',
    filename VARCHAR(255) NOT NULL COMMENT '文件名',
    cos_url VARCHAR(512) NOT NULL COMMENT '腾讯云COS存储URL',
    content_type VARCHAR(128) COMMENT '文件MIME类型',
    file_size INT COMMENT '文件大小(字节)',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='任务生成文件表';

-- 创建索引以提高查询性能
CREATE INDEX idx_tasks_user_id ON tasks(user_id) COMMENT '用户ID索引，加速按用户查询任务';
CREATE INDEX idx_files_task_id ON files(task_id) COMMENT '任务ID索引，加速查询任务关联的文件';

-- 示例数据(可选)
-- INSERT INTO tasks (user_id, prompt, status, log_url) VALUES ('user1', '创建一个Python爬虫', 'pending', null);
-- INSERT INTO tasks (user_id, prompt, status, log_url) VALUES ('user1', '生成一个React组件', 'completed', 'https://bucket.cos.ap-nanjing.myqcloud.com/logs/task_2_log.txt'); 