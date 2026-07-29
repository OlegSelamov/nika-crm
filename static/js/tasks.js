(function () {
    const modal = document.getElementById('taskModal');
    if (modal && modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.task-menu-btn') &&
            !event.target.closest('.task-menu')) {
            closeTaskMenus();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeTaskModal();
    });
})();

function openTaskModal() {
    const form = document.getElementById('taskForm');
    form.reset();
    form.action = '/tasks/add';
    document.getElementById('taskModalTitle').textContent = 'Новая задача';
    document.getElementById('taskStatusField').style.display = 'none';
    document.getElementById('taskPriority').value = 'medium';

    document.getElementById('taskModal').classList.add('is-open');
    document.body.classList.add('task-modal-open');
}

function closeTaskModal() {
    const modal = document.getElementById('taskModal');
    if (!modal) return;
    modal.classList.remove('is-open');
    document.body.classList.remove('task-modal-open');
}

function editTask(task) {
    const form = document.getElementById('taskForm');
    form.action = '/tasks/' + task.id + '/edit';

    document.getElementById('taskModalTitle').textContent = 'Редактировать задачу';
    document.getElementById('taskTitle').value = task.title || '';
    document.getElementById('taskDescription').value = task.description || '';
    document.getElementById('taskAssignee').value = task.assignee_id || '';
    document.getElementById('taskDueDate').value = task.due_date || '';
    document.getElementById('taskPriority').value = task.priority || 'medium';
    document.getElementById('taskStatus').value = task.status || 'new';
    document.getElementById('taskStatusField').style.display = 'grid';

    document.getElementById('taskModal').classList.add('is-open');
    document.body.classList.add('task-modal-open');
    closeTaskMenus();
}

function toggleTaskMenu(button) {
    const menu = button.nextElementSibling;
    const wasOpen = menu.classList.contains('is-open');
    closeTaskMenus();
    if (!wasOpen) menu.classList.add('is-open');
}

function closeTaskMenus() {
    document.querySelectorAll('.task-menu.is-open').forEach(menu => {
        menu.classList.remove('is-open');
    });
}

async function changeTaskStatus(taskId, select) {
    const previous = select.dataset.previous || select.value;
    const body = new URLSearchParams({ status: select.value });

    try {
        const response = await fetch('/tasks/' + taskId + '/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        });

        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка');

        select.dataset.previous = select.value;
        window.location.reload();
    } catch (error) {
        select.value = previous;
        alert(error.message);
    }
}