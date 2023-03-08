window.onload = function(){
    // esconde campo timefield para trabalhar campo dinamico 
    // field-horarios e atribuir o valor por debaixo dos panos.
    document.getElementsByClassName('field-hora_agendada')[0].style.display = "none";

    let fieldset = document.getElementsByTagName('fieldset')[0]
    let inputObs = document.getElementsByClassName('field-observacao')[0];
    
    let divSelectHorarios = document.createElement('div');
    divSelectHorarios.id = 'block';
    divSelectHorarios.className = 'form-row field-horarios';
    
    let label = document.createElement('label')
    label.class = "required"
    label.for = "id_select_hora_agendada"
    label.innerHTML = "Horários disponíveis:"

    let select = document.createElement('select');
    select.name= "select_hora_agendada"
    select.id = id="id_select_hora_agendada"
    select.required = true
    select.onchange = onChangeSelect

    divSelectHorarios.appendChild(label);
    divSelectHorarios.appendChild(select);

    appendDefaultOption(select);

    fieldset.insertBefore(divSelectHorarios, inputObs);

    setupChangeForm();
};

function onChangeSelect(){
    let select = document.getElementById('id_select_hora_agendada');
    let inputHoraAgendada = document.getElementById('id_hora_agendada');
    inputHoraAgendada.value = select.value;
};

// ON UPDATE FORM
function setupChangeForm(){
    let inputHoraAgendada = document.getElementById('id_hora_agendada');
    if (inputHoraAgendada.value){
        onChangeDate()
        appendOptionSelected(inputHoraAgendada.value)
    }
}
function appendOptionSelected(value) { 
    let select = document.getElementById('id_select_hora_agendada');
    let opt = document.createElement('option');
    opt.value = value
    opt.innerHTML = value
    opt.selected = true;
    select.appendChild(opt);    
}

function appendOptions(list) {
    let select = document.getElementById('id_select_hora_agendada');
    
    if(list.length){
        for(let i = 0; i < list.length; i++){
            let opt = document.createElement('option');
            opt.value = list[i]
            opt.innerHTML = list[i]
            select.appendChild(opt);
        }
    } else {
        removeAllChildNodes(select);
        appendDefaultOption(select);
    }
};

function appendDefaultOption(select) {
    var default_option = document.createElement('option');
    default_option.value = ""
    default_option.selected
    default_option.innerHTML = "---------"
    select.appendChild(default_option)
};

function removeAllChildNodes(parent) {
    while (parent.firstChild) {
        parent.removeChild(parent.firstChild);
    }
}

function onChangeDate(){
    inputDate = document.getElementById("id_data_agendada");

    fetch(`http://localhost:8000/api/agenda/horarios_disponiveis/?data=${inputDate.value}`)
    .then(function(response) {
        return response.json();
    })
    .then(function(data) {
        appendOptions(data);
    })
    .catch()
};