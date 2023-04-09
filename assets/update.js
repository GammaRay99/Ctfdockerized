CTFd.plugin.run((_CTFd) => {
    const $ = _CTFd.lib.$
    const md = _CTFd.lib.markdown()
})

let default_server = 0;

let servers_images = {}



function update_images() {
    let img_options = $('#image_select')
    let new_docker = $("#server_select")[0].value;
    var images = servers_images[new_docker];
    img_options.empty();
    if (images == undefined) {
        return;
    } else {
        var images_list = images.split(',')
        for (var i = 0; i < images_list.length; i++) {
            img_options.append($('<option></option>').attr('value', images_list[i]).text(images_list[i]));
            if (images_list[i] == docker_image) {
                img_options.prop('selectedIndex', i);
            }
        }
    }
}


let server_options = $('#server_select');
let index = 0; // ... sorry
$.getJSON("/admin/ctfdockerized/docker-servers/?data=json", function(result){        
    $.each(result, function (key, value) {
        if (value.id == docker_server) {
            server_options.prop('selectedIndex', index);
        }
        server_options.append($('<option></option>').attr('value', value.id).text(key));
        servers_images[value.id] = value.img;
        index++;
    })
    update_images();
});


$("#server_select").change(update_images)
