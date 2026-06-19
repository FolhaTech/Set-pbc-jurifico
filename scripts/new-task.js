var allLinks = document.querySelectorAll("a");
for (var i = 0; i < allLinks.length; i++) {
  if (allLinks[i].innerText.trim() === "Nova tarefa") {
    allLinks[i].scrollIntoView({ block: "center" });
    allLinks[i].click();
    return true;
  }
}
return false;
