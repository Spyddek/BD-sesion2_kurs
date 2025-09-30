import psycopg2
from psycopg2 import sql

DB_NAME = "staff_control"
DB_USER = "postgres"
DB_PASSWORD = "23565471"
DB_HOST = "localhost"
DB_PORT = "5432"

schema_sql = """
CREATE TABLE IF NOT EXISTS departments (
    department_id SERIAL PRIMARY KEY,
    name           VARCHAR(120) NOT NULL UNIQUE,
    phone          VARCHAR(30),
    location       VARCHAR(120)
);
COMMENT ON TABLE departments IS 'Отделы организации';
COMMENT ON COLUMN departments.department_id IS 'Идентификатор отдела';
COMMENT ON COLUMN departments.name IS 'Название отдела';
COMMENT ON COLUMN departments.phone IS 'Телефон отдела';
COMMENT ON COLUMN departments.location IS 'Адрес/расположение';

CREATE TABLE IF NOT EXISTS positions (
    position_id  SERIAL PRIMARY KEY,
    title        VARCHAR(120) NOT NULL,
    hourly_rate  NUMERIC(10,2) NOT NULL CHECK (hourly_rate >= 0),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE positions IS 'Должности сотрудников';
COMMENT ON COLUMN positions.position_id IS 'Идентификатор должности';
COMMENT ON COLUMN positions.title IS 'Название должности';
COMMENT ON COLUMN positions.hourly_rate IS 'Почасовая ставка';
COMMENT ON COLUMN positions.is_active IS 'Активна ли должность';

CREATE TABLE IF NOT EXISTS employees (
    employee_id   SERIAL PRIMARY KEY,
    full_name     VARCHAR(150) NOT NULL,
    birth_date    DATE,
    hire_date     DATE NOT NULL,
    email         VARCHAR(150) UNIQUE,
    phone         VARCHAR(30),
    department_id INTEGER REFERENCES departments(department_id) ON DELETE SET NULL,
    position_id   INTEGER REFERENCES positions(position_id) ON DELETE SET NULL,
    employment_type VARCHAR(30) NOT NULL DEFAULT 'full-time',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE employees IS 'Сотрудники организации';
COMMENT ON COLUMN employees.employee_id IS 'Идентификатор сотрудника';
COMMENT ON COLUMN employees.full_name IS 'ФИО сотрудника';
COMMENT ON COLUMN employees.birth_date IS 'Дата рождения';
COMMENT ON COLUMN employees.hire_date IS 'Дата приёма на работу';
COMMENT ON COLUMN employees.email IS 'Электронная почта';
COMMENT ON COLUMN employees.phone IS 'Телефон';
COMMENT ON COLUMN employees.department_id IS 'Отдел, в котором работает сотрудник';
COMMENT ON COLUMN employees.position_id IS 'Должность сотрудника';
COMMENT ON COLUMN employees.employment_type IS 'Тип занятости (full-time, part-time, contract)';
COMMENT ON COLUMN employees.is_active IS 'Признак активного сотрудника';

CREATE TABLE IF NOT EXISTS work_schedules (
    schedule_id   SERIAL PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    weekday       INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    planned_hours NUMERIC(4,2) NOT NULL CHECK (planned_hours >= 0 AND planned_hours <= 24)
);
COMMENT ON TABLE work_schedules IS 'Плановые графики работы сотрудников';
COMMENT ON COLUMN work_schedules.schedule_id IS 'Идентификатор графика';
COMMENT ON COLUMN work_schedules.employee_id IS 'Сотрудник';
COMMENT ON COLUMN work_schedules.weekday IS 'День недели (0=Пн .. 6=Вс)';
COMMENT ON COLUMN work_schedules.planned_hours IS 'Плановое количество часов';

CREATE TABLE IF NOT EXISTS timesheets (
    timesheet_id  SERIAL PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    work_date     DATE NOT NULL,
    hours_worked  NUMERIC(5,2) NOT NULL CHECK (hours_worked >= 0 AND hours_worked <= 24),
    overtime_hours NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (overtime_hours >= 0 AND overtime_hours <= 24),
    notes         TEXT,
    CONSTRAINT uq_timesheet UNIQUE (employee_id, work_date)
);
COMMENT ON TABLE timesheets IS 'Табель учёта рабочего времени';
COMMENT ON COLUMN timesheets.timesheet_id IS 'Идентификатор записи табеля';
COMMENT ON COLUMN timesheets.employee_id IS 'Сотрудник';
COMMENT ON COLUMN timesheets.work_date IS 'Дата рабочего дня';
COMMENT ON COLUMN timesheets.hours_worked IS 'Количество отработанных часов';
COMMENT ON COLUMN timesheets.overtime_hours IS 'Количество часов переработки';
COMMENT ON COLUMN timesheets.notes IS 'Примечания';

CREATE TABLE IF NOT EXISTS leaves (
    leave_id      SERIAL PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    start_date    DATE NOT NULL,
    end_date      DATE NOT NULL,
    leave_type    VARCHAR(40) NOT NULL CHECK (leave_type IN ('vacation','sick','unpaid','maternity','other')),
    status        VARCHAR(20) NOT NULL DEFAULT 'approved' CHECK (status IN ('approved','pending','rejected')),
    comment       TEXT,
    CONSTRAINT chk_dates CHECK (end_date >= start_date)
);
COMMENT ON TABLE leaves IS 'Отпуска и больничные сотрудников';
COMMENT ON COLUMN leaves.leave_id IS 'Идентификатор отпуска';
COMMENT ON COLUMN leaves.employee_id IS 'Сотрудник';
COMMENT ON COLUMN leaves.start_date IS 'Дата начала отпуска';
COMMENT ON COLUMN leaves.end_date IS 'Дата окончания отпуска';
COMMENT ON COLUMN leaves.leave_type IS 'Тип: vacation=отпуск, sick=больничный, unpaid=неоплачиваемый и т.д.';
COMMENT ON COLUMN leaves.status IS 'Статус (approved=утвержден, pending=на рассмотрении, rejected=отклонен)';
COMMENT ON COLUMN leaves.comment IS 'Комментарий';

CREATE TABLE IF NOT EXISTS payrolls (
    payroll_id    SERIAL PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    period_year   INTEGER NOT NULL CHECK (period_year BETWEEN 2000 AND 2100),
    period_month  INTEGER NOT NULL CHECK (period_month BETWEEN 1 AND 12),
    base_pay      NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (base_pay >= 0),
    overtime_pay  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (overtime_pay >= 0),
    bonus_pay     NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (bonus_pay >= 0),
    deductions    NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (deductions >= 0),
    total_pay     NUMERIC(12,2),
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_payroll UNIQUE (employee_id, period_year, period_month)
);
COMMENT ON TABLE payrolls IS 'Начисления заработной платы';
COMMENT ON COLUMN payrolls.payroll_id IS 'Идентификатор начисления';
COMMENT ON COLUMN payrolls.employee_id IS 'Сотрудник';
COMMENT ON COLUMN payrolls.period_year IS 'Год начисления';
COMMENT ON COLUMN payrolls.period_month IS 'Месяц начисления';
COMMENT ON COLUMN payrolls.base_pay IS 'Базовая зарплата';
COMMENT ON COLUMN payrolls.overtime_pay IS 'Оплата переработки';
COMMENT ON COLUMN payrolls.bonus_pay IS 'Премии';
COMMENT ON COLUMN payrolls.deductions IS 'Удержания';
COMMENT ON COLUMN payrolls.total_pay IS 'Итоговая сумма (оклад+переработка+премия-удержания)';
COMMENT ON COLUMN payrolls.created_at IS 'Дата создания записи';

-- Представление для удобного просмотра сотрудников
CREATE OR REPLACE VIEW v_employee_basic AS
SELECT e.employee_id, e.full_name, e.email,
       d.name AS department, p.title AS position
FROM employees e
LEFT JOIN departments d ON d.department_id = e.department_id
LEFT JOIN positions p ON p.position_id = e.position_id;
COMMENT ON VIEW v_employee_basic IS 'Сводная информация о сотрудниках (ФИО, почта, отдел, должность)';
"""

def create_schema():
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        host=DB_HOST, port=DB_PORT
    )
    cur = conn.cursor()

    cur.execute("SET datestyle = 'ISO, DMY';")
    
    cur.execute(schema_sql)
    conn.commit()
    cur.close()
    conn.close()
    print("Схема базы данных создана.")

if __name__ == "__main__":
    create_schema()