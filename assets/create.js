console.log("hello world!")


CTFd.plugin.run((_CTFd) => {
    const $ = _CTFd.lib.$
    const md = _CTFd.lib.markdown()
})



let servers_images = {}

let server_options = $('#server_select');
let flag = 0; // sorry
let index = 0; // ... sorry
$.getJSON("/admin/ctfdockerized/docker-servers/?data=json", function(result){        
    $.each(result, function (key, value) {
        if (flag = 0) {
            server_options.prop('selectedIndex', index);
            flag = 1337;
        }
        server_options.append($('<option></option>').attr('value', value.id).text(key));
        servers_images[value.id] = value.img;
        index++;
    })
});


let img_options = $('#image_select')
let servers = document.getElementById('server_select');
servers.onchange = (event) => {
    var new_docker = event.target.value;
    var images = servers_images[new_docker];
    if (images == undefined) {
        img_options.empty();
    } else {
        var images_list = images.split(',')
        for (var i = 0; i < images_list.length; i++) {
            if (i == 0) {
                img_options.prop('selectedIndex', i);
            }
            img_options.append($('<option></option>').attr('value', images_list[i]).text(images_list[i]));
        }
    }
}

